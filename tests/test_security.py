"""Regressões da revisão de segurança (#3)."""
import re

import pytest

from inventory.extensions import db
from inventory.models.user import User
from inventory.models.ticket import Ticket
from inventory.repositories import ticket_repo

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        Ticket.query.filter(Ticket.title.like(f"{MARK}%")).delete()
        User.query.filter(User.name.like(f"{MARK}%")).delete()
        db.session.commit()


def test_csp_uses_nonce_and_drops_unsafe_inline(app):
    """S-CSP: script-src usa nonce por request (e NÃO 'unsafe-inline'); o nonce
    do header tem que ser o mesmo dos <script> renderizados."""
    client = app.test_client()
    r = client.get("/login")
    csp = r.headers.get("Content-Security-Policy", "")
    script_src = re.search(r"script-src[^;]*", csp)
    assert script_src, "CSP sem script-src"
    assert "'unsafe-inline'" not in script_src.group(0)
    assert "object-src 'none'" in csp

    nonce = re.search(r"'nonce-([\w-]+)'", script_src.group(0))
    assert nonce, "script-src sem nonce"
    html = r.get_data(as_text=True)
    assert set(re.findall(r'<script nonce="([\w-]+)"', html)) == {nonce.group(1)}

    # o nonce precisa ser novo a cada resposta
    r2 = client.get("/login")
    n2 = re.search(r"'nonce-([\w-]+)'", r2.headers.get("Content-Security-Policy", ""))
    assert n2 and n2.group(1) != nonce.group(1)


def test_kiox_map_has_its_own_csp(auth_client):
    """O mapa KioX é servido cru (sem Jinja), então não tem nonce: precisa do
    CSP próprio com 'unsafe-inline', senão o JS dele (e o login) não roda."""
    r = auth_client.get("/kiox")
    if r.status_code == 404:
        pytest.skip("mapa do KioX não está presente nesta instalação")
    assert r.status_code == 200
    csp = r.headers.get("Content-Security-Policy", "")
    script_src = re.search(r"script-src[^;]*", csp)
    assert script_src and "'unsafe-inline'" in script_src.group(0)
    assert "nonce-" not in csp                     # página crua não tem nonce
    assert "https://*.firebaseio.com" in csp       # Firebase (dados da frota)
    assert "nominatim.openstreetmap.org" in csp    # geocoding


def test_ticket_authz_binds_requester_by_stable_id(app):
    """S4: o solicitante é vinculado por id (não pelo nome, que é mutável).
    Assim, renomear-se no perfil não dá acesso ao chamado de outra pessoa."""
    with app.app_context():
        u = User(name=f"{MARK} Solicitante", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id

        t = ticket_repo.create_ticket(
            opened_by_id=None, title=f"{MARK} chamado", status="aberto",
            requester=f"{MARK} Solicitante")
        assert t.requester_id == uid   # vínculo estável por id

        # Solicitante em texto livre sem cadastro → sem vínculo (ninguém herda).
        t2 = ticket_repo.create_ticket(
            opened_by_id=None, title=f"{MARK} sem dono", status="aberto",
            requester="Zzz Inexistente Qwerty")
        assert t2.requester_id is None
