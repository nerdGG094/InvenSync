"""
Paginação simples sobre listas já carregadas em memória.

A maioria dos módulos monta a lista em Python (repositórios que retornam
`.all()` com ordenação/agregação própria). Em vez de reescrever cada query
para usar `Query.paginate()`, fatiamos a lista pronta e devolvemos os metadados
de página — uniforme para todas as telas em formato de tabela.

Uso na rota:
    from ..services.pagination import paginate
    items, pag = paginate(items)            # 20 por página (padrão)
    return render_template(..., items=items, pag=pag)

No template (ver macro `pager` em templates/_macros.html):
    {% from "_macros.html" import pager %}
    ...{{ pager(pag) }}
"""
from flask import request

DEFAULT_PER_PAGE = 20
PER_PAGE_OPTIONS = (20, 50, 100)


def paginate(items, per_page: int = DEFAULT_PER_PAGE, arg: str = "page",
             per_page_arg: str = "per_page"):
    """Fatia `items` na página atual (lida de `?page=`) e devolve (slice, meta).

    O tamanho da página pode ser escolhido via `?per_page=` (20/50/100).
    `meta` traz: page, pages, total, per_page, per_page_options, has_prev,
    has_next. A página é sempre normalizada para o intervalo válido.
    """
    try:
        req_pp = int(request.args.get(per_page_arg, per_page))
        if req_pp in PER_PAGE_OPTIONS:
            per_page = req_pp
    except (TypeError, ValueError):
        pass

    items = list(items)
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    try:
        page = int(request.args.get(arg, 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    page_items = items[start:start + per_page]
    meta = {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": per_page,
        "per_page_options": list(PER_PAGE_OPTIONS),
        "has_prev": page > 1,
        "has_next": page < pages,
    }
    return page_items, meta
