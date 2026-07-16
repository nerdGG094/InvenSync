"""Regressões da revisão de segurança (#3)."""
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
