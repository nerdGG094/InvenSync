"""Admin → Documentação (viva) do sistema.

Acesso ADMIN-only. A página é montada por introspecção do app em tempo de
request (rotas, blueprints, modelos, serviços, repositórios e tabelas), então
acompanha o código. A seção de arquitetura/diagramas vem de
`docs/DOCUMENTACAO.md` (Mermaid renderizado no navegador).
"""
from flask import Blueprint, render_template, current_app, abort
from flask_login import login_required, current_user

from ..services import docs as docs_service

bp = Blueprint("docs", __name__)


@bp.route("")
@login_required
def index():
    if not current_user.is_admin:
        abort(403)
    dados = docs_service.introspectar(current_app)
    doc_html = docs_service.doc_arquitetura_html()
    return render_template("docs/index.html", d=dados, doc_html=doc_html)
