# inventory/routes/search.py — busca global (omnibox / Ctrl+K), somente admin
from flask import Blueprint, request, jsonify, url_for, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from ..models.product import Product
from ..models.machine import Machine
from ..models.mobile import MobileDevice
from ..models.ticket import Ticket
from ..models.user import User
from ..models.chip import SimChip
from ..models.license import License

bp = Blueprint("search", __name__)

LIMIT = 6  # resultados por categoria


@bp.route("")
@login_required
def api():
    if not current_user.is_admin:
        abort(403)
    q = (request.args.get("q") or "").strip()
    out = []
    if len(q) < 2:
        return jsonify(results=out)
    like = f"%{q}%"

    def add(grupo, icon, rows, titulo, sub, endpoint, **idarg):
        for r in rows:
            out.append({
                "grupo": grupo, "icon": icon,
                "titulo": titulo(r), "sub": sub(r) or "",
                "url": url_for(endpoint, **{k: getattr(r, v) for k, v in idarg.items()}),
            })

    add("Materiais", "bi-box-seam",
        Product.query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like))).limit(LIMIT),
        lambda p: p.name, lambda p: p.sku, "products.edit", pid="id")

    add("Máquinas", "bi-pc-display",
        Machine.query.filter(or_(Machine.model.ilike(like), Machine.name.ilike(like),
                                 Machine.ip_address.ilike(like), Machine.assigned_user.ilike(like),
                                 Machine.patrimony.ilike(like), Machine.serial_number.ilike(like))).limit(LIMIT),
        lambda m: m.model or m.name or "—", lambda m: m.assigned_user or m.ip_address, "machines.edit", mid="id")

    add("Celulares", "bi-phone",
        MobileDevice.query.filter(or_(MobileDevice.model.ilike(like), MobileDevice.phone_number.ilike(like),
                                      MobileDevice.imei.ilike(like), MobileDevice.assigned_employee.ilike(like),
                                      MobileDevice.patrimony.ilike(like))).limit(LIMIT),
        lambda d: f"{d.brand or ''} {d.model}".strip(), lambda d: d.assigned_employee or d.phone_number, "mobile.edit", mid="id")

    add("Chips", "bi-sim",
        SimChip.query.filter(or_(SimChip.phone_number.ilike(like), SimChip.iccid.ilike(like),
                                 SimChip.assigned_employee.ilike(like))).limit(LIMIT),
        lambda c: c.phone_number, lambda c: c.assigned_employee or c.carrier, "chips.edit", cid="id")

    add("Chamados", "bi-headset",
        Ticket.query.filter(or_(Ticket.code.ilike(like), Ticket.title.ilike(like),
                                Ticket.requester.ilike(like))).limit(LIMIT),
        lambda t: f"{t.code} — {t.title}", lambda t: t.requester, "tickets.detail", tid="id")

    add("Colaboradores", "bi-person-vcard",
        User.query.filter(or_(User.name.ilike(like), User.email.ilike(like),
                              User.sector.ilike(like))).limit(LIMIT),
        lambda u: u.name, lambda u: u.sector or u.email, "colaboradores.edit", cid="id")

    add("Licenças", "bi-patch-check",
        License.query.filter(or_(License.name.ilike(like), License.vendor.ilike(like))).limit(LIMIT),
        lambda l: l.name, lambda l: l.vendor, "licenses.edit", lid="id")

    return jsonify(results=out)
