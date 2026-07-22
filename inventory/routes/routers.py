# inventory/routes/routers.py
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   jsonify, abort, current_app)
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..repositories import router_repo
from ..forms.router import RouterForm
from ..models.router import Router
from ..services import audit, crypto, router_ctl

bp = Blueprint("routers", __name__)


@bp.before_request
@login_required
def _only_admin():
    # Painel de roteadores expõe credenciais de gerência: restrito a admin.
    if not current_user.is_admin:
        abort(403)


def _to_kwargs(form: RouterForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        label=s(form.label.data),
        brand=s(form.brand.data),
        model=(form.model.data or "").strip(),
        location=s(form.location.data),
        serial_number=s(form.serial_number.data),
        patrimony=s(form.patrimony.data),
        ip_address=s(form.ip_address.data),
        mac_address=s(form.mac_address.data),
        admin_user=s(form.admin_user.data),
        admin_password=s(form.admin_password.data),
        ssid=s(form.ssid.data),
        wifi_password=s(form.wifi_password.data),
        ssid_guest=s(form.ssid_guest.data),
        wifi_password_guest=s(form.wifi_password_guest.data),
        mac_filtering=bool(form.mac_filtering.data),
        linked_macs=s(form.linked_macs.data),
        status=form.status.data or "em_uso",
        notes=s(form.notes.data),
        label_applied=bool(form.label_applied.data),
    )


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    items = router_repo.list_routers(q or None, status or None)
    counts = dict(db.session.query(Router.status, func.count(Router.id))
                  .group_by(Router.status).all())
    totals = {
        "em_uso": counts.get("em_uso", 0),
        "disponivel": counts.get("disponivel", 0),
        "manutencao": counts.get("manutencao", 0),
        "inativo": counts.get("inativo", 0),
        "total": sum(counts.values()),
    }
    return render_template("routers/list.html", items=items, q=q, status=status, totals=totals)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = RouterForm()
    if form.validate_on_submit():
        r = router_repo.create_router(**_to_kwargs(form))
        audit.record("create", "router", r.id, f"Cadastrou roteador '{r.label or r.model}'")
        flash("Roteador cadastrado!", "success")
        return redirect(url_for("routers.list_view"))
    return render_template("routers/form.html", form=form, title="Novo Roteador")


@bp.route("/<int:rid>/edit", methods=["GET", "POST"])
def edit(rid):
    r = router_repo.get_router(rid)
    form = RouterForm(obj=r)
    if request.method == "GET":
        # Não expõe as senhas cifradas nos campos; em branco ao salvar = manter.
        form.admin_password.data = ""
        form.wifi_password.data = ""
        form.wifi_password_guest.data = ""
    if form.validate_on_submit():
        router_repo.update_router(r, **_to_kwargs(form))
        audit.record("update", "router", r.id, f"Alterou roteador '{r.label or r.model}'")
        flash("Roteador atualizado!", "success")
        return redirect(url_for("routers.list_view"))
    return render_template("routers/form.html", form=form, title="Editar Roteador")


@bp.route("/<int:rid>/delete", methods=["POST"])
def delete(rid):
    r = router_repo.get_router(rid)
    audit.record("delete", "router", r.id, f"Excluiu roteador '{r.label or r.model}'")
    router_repo.delete_router(r)
    flash("Roteador excluído.", "success")
    return redirect(url_for("routers.list_view"))


# ---------------------------------------------------------------------------
# Painel de controle (AJAX): status ao vivo, acesso direto e revelar senha.
# ---------------------------------------------------------------------------
@bp.route("/<int:rid>/status")
def status(rid):
    """Estado do painel admin ao vivo (online/latência) + como ele autentica.
    Consumido por AJAX no card — é consulta de rede e não pode travar a página."""
    r = router_repo.get_router(rid)
    if not (r.ip_address or "").strip():
        return jsonify(online=False, auth_kind="sem-ip", latency_ms=None)
    dados = router_ctl.probe(
        r.ip_address, timeout=float(current_app.config.get("ROUTER_PROBE_TIMEOUT", 4)))
    return jsonify(dados)


@bp.route("/<int:rid>/senha")
def senha(rid):
    """Devolve a senha decifrada (admin ou Wi-Fi) para revelar/copiar, e registra
    quem acessou na auditoria."""
    tipo = (request.args.get("tipo") or "admin").strip()
    field = {"admin": "admin_password", "wifi": "wifi_password"}.get(tipo, "admin_password")
    rotulo = "senha admin" if field == "admin_password" else "senha Wi-Fi"
    r = router_repo.get_router(rid)
    if not audit.record("reveal", "router", r.id,
                        f"Revelou {rotulo} do roteador '{r.label or r.model}'"):
        return jsonify(error="Falha ao registrar auditoria; exibição cancelada."), 503
    try:
        return jsonify(user=r.admin_user or "",
                       password=crypto.decrypt(getattr(r, field)) or "")
    except crypto.DecryptError:
        return jsonify(error="Não foi possível decifrar (VAULT_KEY incorreta?)."), 500
