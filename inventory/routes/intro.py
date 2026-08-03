# inventory/routes/intro.py — Apresentação (tela de boas-vindas do sistema)
"""Página de apresentação do InvenSync.

Aberta automaticamente na PRIMEIRA entrada de cada pessoa (veja
`routes/auth.py::_home_for`) e depois sempre acessível pelo menu, logo acima
do Painel. Disponível para todo mundo — inclusive usuários comuns, por isso o
prefixo `intro.` está em `NON_ADMIN_PREFIXES`.

A cena 3D e as animações são carregadas SÓ aqui (Three.js e GSAP entram por
CDN no bloco de scripts do template), então nenhuma outra tela paga por elas.
"""
from flask import Blueprint, render_template, url_for
from flask_login import login_required, current_user

from ..extensions import db

bp = Blueprint("intro", __name__)


def _destino():
    """Para onde o botão final leva: a tela inicial de cada perfil."""
    if current_user.is_admin:
        return url_for("dashboard.index"), "Ir para o Painel"
    return url_for("announcements.list_view"), "Ir para os Avisos"


@bp.route("")
@login_required
def index():
    """Mostra a apresentação e marca que esta pessoa já a viu.

    A marcação acontece na primeira abertura — inclusive quando a página é
    aberta pelo menu — para que o login deixe de ser interceptado. É
    best-effort: falhar ao gravar não pode impedir a página de abrir."""
    if not getattr(current_user, "intro_visto", True):
        try:
            current_user.intro_visto = True
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
    destino, rotulo = _destino()
    return render_template("intro/index.html", destino=destino, destino_rotulo=rotulo)
