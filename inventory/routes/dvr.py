# inventory/routes/dvr.py — CFTV / DVRs (admin): inventário + status + abrir painel + câmeras
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   jsonify, abort, current_app, Response)
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..repositories import dvr_repo
from ..forms.dvr import DvrForm
from ..models.dvr import Dvr
from ..services import audit, crypto, router_ctl, dvr_cam

bp = Blueprint("dvr", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _norm_mac(v):
    hexd = "".join(c for c in (v or "").lower() if c in "0123456789abcdef")
    if len(hexd) != 12:
        return ((v or "").strip().lower().replace(":", "-")) or None
    return "-".join(hexd[i:i + 2] for i in range(0, 12, 2))


def _to_kwargs(form: DvrForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        label=s(form.label.data), brand=s(form.brand.data),
        model=(form.model.data or "").strip(), serial_number=s(form.serial_number.data),
        patrimony=s(form.patrimony.data), ip_address=s(form.ip_address.data),
        web_port=form.web_port.data or None, mac_address=_norm_mac(form.mac_address.data),
        admin_user=s(form.admin_user.data), admin_password=s(form.admin_password.data),
        channels=form.channels.data or None, location=s(form.location.data),
        status=form.status.data or "em_uso", notes=s(form.notes.data),
    )


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    items = dvr_repo.list_dvrs(q or None, status or None)
    counts = dict(db.session.query(Dvr.status, func.count(Dvr.id)).group_by(Dvr.status).all())
    totals = {"em_uso": counts.get("em_uso", 0), "manutencao": counts.get("manutencao", 0),
              "inativo": counts.get("inativo", 0), "total": sum(counts.values())}
    return render_template("cftv/list.html", items=items, q=q, status=status, totals=totals)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = DvrForm()
    if form.validate_on_submit():
        d = dvr_repo.create_dvr(**_to_kwargs(form))
        audit.record("create", "dvr", d.id, f"Cadastrou DVR '{d.label or d.model}'")
        flash("DVR cadastrado!", "success")
        return redirect(url_for("dvr.list_view"))
    return render_template("cftv/form.html", form=form, title="Novo DVR")


@bp.route("/<int:did>/edit", methods=["GET", "POST"])
def edit(did):
    d = dvr_repo.get_dvr(did)
    form = DvrForm(obj=d)
    if request.method == "GET":
        form.admin_password.data = ""   # não expõe a senha; em branco = manter
    if form.validate_on_submit():
        dvr_repo.update_dvr(d, **_to_kwargs(form))
        audit.record("update", "dvr", d.id, f"Alterou DVR '{d.label or d.model}'")
        flash("DVR atualizado!", "success")
        return redirect(url_for("dvr.list_view"))
    return render_template("cftv/form.html", form=form, title="Editar DVR")


@bp.route("/<int:did>/delete", methods=["POST"])
def delete(did):
    d = dvr_repo.get_dvr(did)
    audit.record("delete", "dvr", d.id, f"Excluiu DVR '{d.label or d.model}'")
    dvr_repo.delete_dvr(d)
    flash("DVR excluído.", "success")
    return redirect(url_for("dvr.list_view"))


def _base_url(d):
    ip = (d.ip_address or "").strip()
    if not ip:
        return ""
    base = ip if "://" in ip else "http://" + ip
    if d.web_port and d.web_port != 80:
        base += f":{d.web_port}"
    return base


@bp.route("/<int:did>/status")
def status(did):
    """Status ao vivo do painel do DVR (online/latência). AJAX no card."""
    d = dvr_repo.get_dvr(did)
    base = _base_url(d)
    if not base:
        return jsonify(online=False, error="sem IP")
    return jsonify(router_ctl.probe(base, timeout=float(current_app.config.get("ROUTER_PROBE_TIMEOUT", 4))))


@bp.route("/<int:did>/senha")
def senha(did):
    """Senha admin decifrada p/ copiar/revelar (auditado)."""
    d = dvr_repo.get_dvr(did)
    if not audit.record("reveal", "dvr", d.id, f"Revelou senha do DVR '{d.label or d.model}'"):
        return jsonify(error="Falha ao registrar auditoria; exibição cancelada."), 503
    try:
        return jsonify(user=d.admin_user or "", password=crypto.decrypt(d.admin_password) or "",
                       url=_base_url(d))
    except crypto.DecryptError:
        return jsonify(error="Não foi possível decifrar (VAULT_KEY incorreta?)."), 500


@bp.route("/<int:did>/cameras")
def cameras(did):
    """Grade de câmeras (snapshots ao vivo) do DVR."""
    d = dvr_repo.get_dvr(did)
    n = d.channels or 1
    audit.record("access", "dvr", d.id, f"Abriu câmeras do DVR '{d.label or d.model}'")
    return render_template("cftv/cameras.html", d=d, canais=list(range(1, n + 1)))


@bp.route("/<int:did>/snap/<int:ch>")
def snap(did, ch):
    """Proxy do snapshot do canal (JPEG em memória — nada é salvo em disco)."""
    d = dvr_repo.get_dvr(did)
    try:
        pw = crypto.decrypt(d.admin_password) or ""
    except crypto.DecryptError:
        abort(500)
    # modo "live" (câmera ampliada): cache mínimo p/ frames o mais atuais possível.
    if request.args.get("live") == "1":
        ttl = float(current_app.config.get("DVR_SNAP_TTL_LIVE", 0.4))
    else:
        ttl = float(current_app.config.get("DVR_SNAP_TTL", 3))
    data = dvr_cam.snapshot(d, pw, ch, ttl=ttl)
    if not data:
        return Response(status=503)   # sem sinal / DVR indisponível
    return Response(data, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store, max-age=0"})
