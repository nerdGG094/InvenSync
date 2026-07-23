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
    configurado = bool((current_app.config.get("MELI_CLIENT_ID") or "").strip()
                       and (current_app.config.get("MELI_CLIENT_SECRET") or "").strip())
    resultado = None
    if q and configurado:
        resultado = mercado_livre.search(current_app, q, novos=novos)
    # Deep-link p/ abrir a mesma busca no SITE do ML, já ordenada por menor
    # preço — funciona sem credenciais (o navegador do admin não é bloqueado).
    ml_url = ("https://lista.mercadolivre.com.br/"
              + q.replace(" ", "-") + "_OrderId_PRICE") if q else ""
    return render_template("cotacoes/list.html", q=q, novos=novos,
                           resultado=resultado, configurado=configurado,
                           ml_url=ml_url)
