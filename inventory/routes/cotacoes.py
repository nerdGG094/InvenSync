# inventory/routes/cotacoes.py
from flask import Blueprint, render_template, request, current_app, abort
from flask_login import login_required, current_user

from ..services import mercado_livre

bp = Blueprint("cotacoes", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def index():
    """Cotações do Mercado Livre: digite uma palavra-chave (ex.: TN3492) e veja
    os melhores preços, do menor para o maior."""
    q = (request.args.get("q") or "").strip()
    novos = (request.args.get("novos", "1") != "0")
    resultado = None
    if q:
        resultado = mercado_livre.search(current_app, q, novos=novos)
    configurado = bool((current_app.config.get("MELI_CLIENT_ID") or "").strip()
                       and (current_app.config.get("MELI_CLIENT_SECRET") or "").strip())
    return render_template("cotacoes/list.html", q=q, novos=novos,
                           resultado=resultado, configurado=configurado)
