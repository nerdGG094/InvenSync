# inventory/routes/backups.py — backups do banco (somente admin/TI)
import datetime
import os
import sys

from flask import Blueprint, render_template, redirect, url_for, flash, abort, send_file
from flask_login import login_required, current_user

from ..services import audit

bp = Blueprint("backups", __name__)

# Garante que backup_db.py (raiz do projeto) seja importável.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def index():
    import backup_db
    items = backup_db.list_backups()
    last = items[0]["mtime"] if items else None
    age_hours = None
    if last:
        age_hours = (datetime.datetime.now() - last).total_seconds() / 3600.0
    return render_template(
        "backups/index.html",
        items=items,
        last=last,
        age_hours=age_hours,
        backup_dir=str(backup_db.backup_dir()),
    )


@bp.route("/download/<path:name>")
def download(name):
    import backup_db
    safe = os.path.basename(name)   # evita path traversal
    path = backup_db.backup_dir() / safe
    if not safe.endswith(".dump") or not path.exists():
        abort(404)
    audit.record("export", "backup", None, f"Baixou backup {safe}")
    return send_file(str(path), as_attachment=True, download_name=safe)


@bp.route("/run", methods=["POST"])
def run():
    import backup_db
    ok, msg, _ = backup_db.run_backup()
    if ok:
        flash(msg, "success")
        audit.record("export", "backup", None, "Backup manual do banco gerado")
    else:
        flash(f"Falha no backup: {msg}", "danger")
    return redirect(url_for("backups.index"))
