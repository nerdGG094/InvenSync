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

# O mapa é uma página AUTOSSUFICIENTE servida crua (sem Jinja), então seus
# <script> inline não recebem o nonce do CSP global — e ficariam bloqueados.
# Damos a ela um CSP próprio, com 'unsafe-inline' restrito A ESTA PÁGINA e as
# origens que ela realmente usa (Leaflet, Firebase, Nominatim). O restante do
# app continua com o CSP estrito por nonce.
KIOX_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com https://www.gstatic.com "
    "https://*.firebaseio.com https://*.googleapis.com; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "img-src 'self' data: blob: https:; "
    "font-src 'self' data: https://unpkg.com; "
    "connect-src 'self' https://*.firebaseio.com wss://*.firebaseio.com "
    "https://*.googleapis.com https://nominatim.openstreetmap.org; "
    "object-src 'none'; frame-ancestors 'self'; base-uri 'self'"
)


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
    # CSP específico do mapa (o global usa nonce, que esta página não tem).
    # Definido aqui: o handler global usa setdefault e não sobrescreve.
    resp.headers["Content-Security-Policy"] = KIOX_CSP
    return resp


@bp.route("/apk")
def apk():
    """Download do APK do KioX (para instalar manualmente ou via ADB)."""
    path = os.path.join(current_app.root_path, "kiox", APK_FILE)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name="app-release.apk",
                     mimetype="application/vnd.android.package-archive")
