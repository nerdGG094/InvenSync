# inventory/routes/errors.py — log central de erros (somente admin/TI)
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..services import errorlog, audit

bp = Blueprint("errors", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def list_view():
    items = errorlog.recent(300)
    return render_template("errors/list.html", items=items, total=errorlog.count())


@bp.route("/clear", methods=["POST"])
def clear():
    audit.record("delete", "error_log", None, "Limpou o log de erros")
    errorlog.clear_all()
    flash("Log de erros limpo.", "success")
    return redirect(url_for("errors.list_view"))
