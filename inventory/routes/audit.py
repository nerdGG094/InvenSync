# inventory/routes/audit.py
from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user

from ..services import audit

bp = Blueprint("audit", __name__)


@bp.route("")
@login_required
def list_view():
    if not current_user.is_admin:
        abort(403)
    action = (request.args.get("action") or "").strip()
    entity = (request.args.get("entity") or "").strip()
    logs = audit.list_logs(limit=400, action=action or None, entity=entity or None)
    return render_template("audit/list.html", logs=logs, action=action, entity=entity)
