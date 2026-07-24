# inventory/routes/rede.py
from flask import Blueprint, render_template, request, current_app, abort
from flask_login import login_required, current_user

from ..models.machine import Machine
from ..services import net_scan

bp = Blueprint("rede", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _match_maps():
    """Mapas p/ casar dispositivo -> máquina cadastrada (por IP fixo e por nome)."""
    por_ip, por_nome = {}, {}
    for m in Machine.query.all():
        ip = (m.ip_address or "").strip()
        if ip and ip.upper() != "DHCP":
            por_ip.setdefault(ip, m)
        for campo in (m.name, m.model):
            c = (campo or "").strip().lower()
            if c:
                por_nome.setdefault(c, m)
    return por_ip, por_nome


@bp.route("")
def index():
    sweep = request.args.get("sweep") == "1"
    dispositivos = net_scan.scan(current_app, sweep=sweep)
    por_ip, por_nome = _match_maps()

    for d in dispositivos:
        host_curto = (d["name"].split(".")[0] if d["name"] else "").lower()
        m = por_ip.get(d["ip"]) or (por_nome.get(host_curto) if host_curto else None)
        d["machine"] = m
        d["machine_label"] = (m.model or m.name) if m else ""
        d["machine_id"] = m.id if m else None

    total = len(dispositivos)
    cadastrados = sum(1 for d in dispositivos if d["machine"])
    return render_template("rede/list.html", dispositivos=dispositivos,
                           total=total, cadastrados=cadastrados,
                           desconhecidos=total - cadastrados, sweep=sweep)
