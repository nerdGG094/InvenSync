# inventory/routes/labels.py
import io

import qrcode
from flask import Blueprint, render_template, request, abort, send_file, url_for
from flask_login import login_required, current_user

from ..models.machine import Machine
from ..models.router import Router
from ..models.mobile import MobileDevice

bp = Blueprint("labels", __name__)

KIND_LABELS = {"computador": "Computador", "notebook": "Notebook", "impressora": "Impressora"}


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _asset_url(kind: str, oid: int) -> str:
    if kind == "machine":
        return url_for("machines.edit", mid=oid, _external=True)
    if kind == "router":
        return url_for("routers.edit", rid=oid, _external=True)
    if kind == "mobile":
        return url_for("mobile.edit", mid=oid, _external=True)
    return url_for("dashboard.index", _external=True)


def _label_for_machine(m: Machine) -> dict:
    return {"kind": "machine", "id": m.id,
            "title": (f"{m.brand or ''} {m.model or ''}").strip() or (m.name or "Máquina"),
            "subtitle": KIND_LABELS.get(m.kind, m.kind),
            "patrimony": m.patrimony, "sector": m.sector, "extra": m.ip_address,
            "applied": bool(getattr(m, "label_applied", False))}


def _label_for_router(r: Router) -> dict:
    return {"kind": "router", "id": r.id,
            "title": (f"{r.brand or ''} {r.model or ''}").strip() or "Roteador",
            "subtitle": "Roteador", "patrimony": r.patrimony,
            "sector": r.location, "extra": r.ip_address,
            "applied": bool(getattr(r, "label_applied", False))}


def _label_for_mobile(d: MobileDevice) -> dict:
    return {"kind": "mobile", "id": d.id,
            "title": (f"{d.brand or ''} {d.model or ''}").strip() or "Celular",
            "subtitle": "Celular", "patrimony": d.patrimony,
            "sector": d.sector, "extra": d.phone_number,
            "applied": bool(getattr(d, "label_applied", False))}


@bp.route("")
def index():
    kind = (request.args.get("kind") or "machine").strip()
    status = (request.args.get("status") or "pendente").strip()  # pendente | colada | todas
    if kind == "router":
        allitems = [_label_for_router(r) for r in Router.query.order_by(Router.location).all()]
    elif kind == "mobile":
        allitems = [_label_for_mobile(d) for d in MobileDevice.query.order_by(MobileDevice.assigned_employee).all()]
    else:
        kind = "machine"
        allitems = [_label_for_machine(m) for m in Machine.query.order_by(Machine.sector).all()]

    totals = {
        "pendente": sum(1 for i in allitems if not i["applied"]),
        "colada": sum(1 for i in allitems if i["applied"]),
        "todas": len(allitems),
    }
    if status == "colada":
        items = [i for i in allitems if i["applied"]]
    elif status == "todas":
        items = allitems
    else:
        status = "pendente"
        items = [i for i in allitems if not i["applied"]]

    return render_template("labels/index.html", items=items, kind=kind,
                           status=status, totals=totals)


@bp.route("/qr/<kind>/<int:oid>.png")
def qr_png(kind, oid):
    if kind not in ("machine", "router", "mobile"):
        abort(404)
    data = _asset_url(kind, oid)
    img = qrcode.make(data, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")
