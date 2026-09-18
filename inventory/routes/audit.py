# inventory/routes/audit.py
from datetime import datetime

from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user

from ..services import audit
from ..services.pagination import PER_PAGE_OPTIONS

bp = Blueprint("audit", __name__)


def _data(valor: str):
    """'2026-09-18' (input type=date) -> datetime; vazio/inválido -> None."""
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        return None


@bp.route("")
@login_required
def list_view():
    if not current_user.is_admin:
        abort(403)

    action = (request.args.get("action") or "").strip()
    entity = (request.args.get("entity") or "").strip()
    user = (request.args.get("user") or "").strip()
    texto = (request.args.get("q") or "").strip()
    inicio_s = (request.args.get("start") or "").strip()
    fim_s = (request.args.get("end") or "").strip()

    query = audit.build_query(action=action or None, entity=entity or None,
                              user=user or None, texto=texto or None,
                              inicio=_data(inicio_s), fim=_data(fim_s))

    # Paginação NO BANCO. A versão anterior trazia 400 linhas e fatiava em
    # memória: o resto da trilha era inalcançável pela tela e o rodapé dizia
    # "400 registros" como se fosse o total.
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 20
    pag = query.paginate(page=page, per_page=per_page, error_out=False)
    pag.per_page_options = list(PER_PAGE_OPTIONS)

    return render_template("audit/list.html", logs=pag.items, pag=pag,
                           action=action, entity=entity, user=user, q=texto,
                           start=inicio_s, end=fim_s,
                           acoes=audit.acoes_registradas())
