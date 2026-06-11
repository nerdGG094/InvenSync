# inventory/routes/wpp.py — conexão do WhatsApp (QR), somente admin (TI)
from flask import Blueprint, render_template, jsonify, abort
from flask_login import login_required, current_user

from ..services import whatsapp

bp = Blueprint("wpp", __name__)


@bp.before_request
def _guard():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@bp.route("")
@login_required
def page():
    return render_template("wpp/connect.html", configured=whatsapp.configured())


@bp.route("/status")
@login_required
def status():
    return jsonify(whatsapp.status())


@bp.route("/start", methods=["POST"])
@login_required
def start():
    return jsonify(whatsapp.start() or {"status": "error"})
