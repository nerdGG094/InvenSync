# inventory/routes/kiox.py — Kiox: mapa de rastreio da frota (admin)
#
# Serve a página autossuficiente do mapa de rastreio (Leaflet + Firebase RTDB),
# copiada da pasta KioX para dentro do projeto. Acesso restrito a administradores.
import os

from flask import Blueprint, abort, current_app, send_file
from flask_login import login_required, current_user

bp = Blueprint("kiox", __name__)

MAP_FILE = "RASTREIO-mapa.html"


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
    return send_file(path)
