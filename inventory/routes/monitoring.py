# inventory/routes/monitoring.py — monitoramento de uptime (somente admin/TI)
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, current_app)
from flask_login import login_required, current_user

from ..extensions import db
from ..models.monitor import MonitoredHost
from ..models.machine import Machine
from ..models.router import Router
from ..services import monitoring, audit

bp = Blueprint("monitoring", __name__)

KIND_CHOICES = [
    ("servidor", "Servidor"), ("impressora", "Impressora"), ("roteador", "Roteador"),
    ("switch", "Switch"), ("site", "Site"), ("outro", "Outro"),
]
CHECK_CHOICES = [("icmp", "Ping (ICMP)"), ("http", "HTTP (GET)")]


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    query = MonitoredHost.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(MonitoredHost.label.ilike(like),
                                    MonitoredHost.host.ilike(like)))
    items = query.order_by(MonitoredHost.last_status.desc(),
                           MonitoredHost.label.asc()).all()
    up = sum(1 for h in items if h.last_status == "up")
    down = sum(1 for h in items if h.last_status == "down")
    unknown = sum(1 for h in items if h.last_status == "unknown")
    interval = int(current_app.config.get("MONITORING_INTERVAL", 120) or 120)
    return render_template("monitoring/list.html", items=items, q=q,
                           up=up, down=down, unknown=unknown,
                           kind_labels=dict(KIND_CHOICES), interval=interval)


def _form_kwargs():
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        label=(request.form.get("label") or "").strip(),
        host=(request.form.get("host") or "").strip(),
        kind=request.form.get("kind") or "servidor",
        check_type=request.form.get("check_type") or "icmp",
        enabled=bool(request.form.get("enabled")),
        notes=s(request.form.get("notes")),
    )


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        data = _form_kwargs()
        if not data["label"] or not data["host"]:
            flash("Informe ao menos o nome e o host/IP.", "warning")
            return render_template("monitoring/form.html", title="Novo Host",
                                   h=data, kinds=KIND_CHOICES, checks=CHECK_CHOICES)
        h = MonitoredHost(**data)
        db.session.add(h)
        db.session.commit()
        audit.record("create", "monitor", h.id, f"Cadastrou host monitorado {h.label} ({h.host})")
        flash("Host adicionado ao monitoramento.", "success")
        return redirect(url_for("monitoring.list_view"))
    # GET — pré-preenche com enabled marcado
    return render_template("monitoring/form.html", title="Novo Host",
                           h={"enabled": True, "kind": "servidor", "check_type": "icmp"},
                           kinds=KIND_CHOICES, checks=CHECK_CHOICES)


@bp.route("/<int:hid>/edit", methods=["GET", "POST"])
def edit(hid):
    h = MonitoredHost.query.get_or_404(hid)
    if request.method == "POST":
        data = _form_kwargs()
        if not data["label"] or not data["host"]:
            flash("Informe ao menos o nome e o host/IP.", "warning")
            return render_template("monitoring/form.html", title=f"Editar {h.label}",
                                   h=h, kinds=KIND_CHOICES, checks=CHECK_CHOICES)
        for k, v in data.items():
            setattr(h, k, v)
        db.session.commit()
        flash("Host atualizado.", "success")
        return redirect(url_for("monitoring.list_view"))
    return render_template("monitoring/form.html", title=f"Editar {h.label}",
                           h=h, kinds=KIND_CHOICES, checks=CHECK_CHOICES)


@bp.route("/<int:hid>/delete", methods=["POST"])
def delete(hid):
    h = MonitoredHost.query.get_or_404(hid)
    label = h.label
    db.session.delete(h)
    db.session.commit()
    audit.record("delete", "monitor", hid, f"Removeu host monitorado {label}")
    flash("Host removido do monitoramento.", "success")
    return redirect(url_for("monitoring.list_view"))


@bp.route("/<int:hid>/toggle", methods=["POST"])
def toggle(hid):
    h = MonitoredHost.query.get_or_404(hid)
    h.enabled = not h.enabled
    if not h.enabled:
        h.last_status = "unknown"
        h.fail_count = 0
    db.session.commit()
    flash(f"Monitoramento de {h.label} {'ativado' if h.enabled else 'pausado'}.", "success")
    return redirect(url_for("monitoring.list_view"))


@bp.route("/check", methods=["POST"])
def check_now():
    """Verifica todos os hosts agora (sob demanda), além do agendador."""
    monitoring.check_all(current_app._get_current_object())
    flash("Verificação executada.", "success")
    return redirect(url_for("monitoring.list_view"))


@bp.route("/import", methods=["POST"])
def import_assets():
    """Adiciona rapidamente hosts a partir de máquinas/roteadores com IP cadastrado."""
    existing = {(h.host or "").strip().lower() for h in MonitoredHost.query.all()}
    added = 0
    for m in Machine.query.filter(Machine.ip_address.isnot(None)).all():
        ip = (m.ip_address or "").strip()
        if ip and ip.lower() not in existing:
            kind = "impressora" if m.kind == "impressora" else "servidor"
            label = m.name or m.model or f"Máquina #{m.id}"
            db.session.add(MonitoredHost(label=label, host=ip, kind=kind, check_type="icmp"))
            existing.add(ip.lower())
            added += 1
    for r in Router.query.filter(Router.ip_address.isnot(None)).all():
        ip = (r.ip_address or "").strip()
        if ip and ip.lower() not in existing:
            label = r.label or r.model or f"Roteador #{r.id}"
            db.session.add(MonitoredHost(label=label, host=ip, kind="roteador", check_type="icmp"))
            existing.add(ip.lower())
            added += 1
    if added:
        db.session.commit()
        flash(f"{added} host(s) importado(s) de máquinas/roteadores.", "success")
    else:
        flash("Nenhum host novo com IP para importar.", "info")
    return redirect(url_for("monitoring.list_view"))
