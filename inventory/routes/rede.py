# inventory/routes/rede.py
from flask import (Blueprint, render_template, request, current_app, abort,
                   jsonify, url_for)
from flask_login import login_required, current_user

from ..extensions import db
from ..models.machine import Machine
from ..services import net_scan, audit

bp = Blueprint("rede", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _match_maps():
    """Mapas p/ casar dispositivo -> máquina: por MAC (certeiro), hostname, IP e nome."""
    por_mac, por_host, por_ip, por_nome = {}, {}, {}, {}
    for m in Machine.query.all():
        mac = (m.mac_address or "").strip().lower()
        if mac:
            por_mac.setdefault(mac, m)
        host = (m.hostname or "").strip().lower()
        if host:
            por_host.setdefault(host, m)
        ip = (m.ip_address or "").strip()
        if ip and ip.upper() != "DHCP":
            por_ip.setdefault(ip, m)
        for campo in (m.name, m.model):
            c = (campo or "").strip().lower()
            if c:
                por_nome.setdefault(c, m)
    return por_mac, por_host, por_ip, por_nome


@bp.route("")
def index():
    # Página abre instantânea; o scan (lento) roda por AJAX ao clicar no botão.
    return render_template("rede/list.html")


@bp.route("/scan")
def scan():
    """Executa a descoberta e devolve JSON. Chamado por AJAX ao clicar no botão."""
    sweep = request.args.get("sweep") == "1"
    dispositivos = net_scan.scan(current_app, sweep=sweep)
    por_mac, por_host, por_ip, por_nome = _match_maps()

    out = []
    for d in dispositivos:
        host = (d["name"].split(".")[0] if d["name"] else "")
        hl = host.lower()
        m = (por_mac.get(d["mac"]) or (por_host.get(hl) if hl else None)
             or por_ip.get(d["ip"]) or (por_nome.get(hl) if hl else None))
        out.append({
            "ip": d["ip"], "mac": d["mac"], "name": d["name"], "host": host,
            "machine_id": m.id if m else None,
            "machine_label": (m.model or m.name) if m else "",
            "machine_url": url_for("machines.edit", mid=m.id) if m else "",
            # já tem MAC salvo? (p/ esconder o botão "salvar")
            "mac_salvo": bool(m and (m.mac_address or "").strip()) if m else False,
        })
    total = len(out)
    cadastrados = sum(1 for d in out if d["machine_id"])
    return jsonify(total=total, cadastrados=cadastrados,
                   desconhecidos=total - cadastrados, dispositivos=out)


@bp.route("/vincular", methods=["POST"])
def vincular():
    """Salva MAC + hostname descobertos no cadastro da máquina (bootstrap do vínculo)."""
    mid = request.form.get("machine_id", type=int)
    mac = (request.form.get("mac") or "").strip().lower()
    host = (request.form.get("host") or "").strip()
    m = db.session.get(Machine, mid) if mid else None
    if not m:
        return jsonify(ok=False, error="Máquina não encontrada."), 404
    if mac:
        m.mac_address = mac
    if host and not (m.hostname or "").strip():
        m.hostname = host
    db.session.commit()
    audit.record("update", "machine", m.id,
                 f"Vinculou MAC {mac} (rede) a '{m.model or m.name}'")
    return jsonify(ok=True)
