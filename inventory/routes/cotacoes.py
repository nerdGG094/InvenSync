# inventory/routes/cotacoes.py
from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user

bp = Blueprint("cotacoes", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def index():
    """Cotações: digite o modelo/equipamento e abra a lista completa no Mercado
    Livre, já ordenada por menor preço (deep-link — não precisa de API)."""
    q = (request.args.get("q") or "").strip()
    ml_url = ("https://lista.mercadolivre.com.br/"
              + q.replace(" ", "-") + "_OrderId_PRICE") if q else ""
    return render_template("cotacoes/list.html", q=q, ml_url=ml_url)
