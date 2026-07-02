# inventory/routes/kiox.py — Kiox: mapa de rastreio da frota (admin)
#
# Serve a página autossuficiente do mapa de rastreio (Leaflet + Firebase RTDB),
# copiada da pasta KioX para dentro do projeto. Acesso restrito a administradores.
import os

from flask import Blueprint, abort, current_app, send_file, make_response
from flask_login import login_required, current_user

bp = Blueprint("kiox", __name__)

MAP_FILE = "RASTREIO-mapa.html"
APK_FILE = "kiox.apk"


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def index():
    path = os.path.join(current_app.root_path, "kiox", MAP_FILE)
    if not os.path.exists(path):
        abort(404)
    # Servido cru (sem Jinja) para não conflitar com o JS/CSS da página.
    # no-cache: garante que TODA máquina receba a versão atual do mapa. Sem isto,
    # um navegador podia rodar uma cópia antiga em cache (ex.: com a sessão
    # Firebase anônima já sem permissão de leitura) e não exibir a frota.
    resp = make_response(send_file(path))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.route("/apk")
def apk():
    """Download do APK do KioX (para instalar manualmente ou via ADB)."""
    path = os.path.join(current_app.root_path, "kiox", APK_FILE)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name="app-release.apk",
                     mimetype="application/vnd.android.package-archive")
