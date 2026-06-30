"""
Testes do módulo de Chamados (helpdesk): criação, fluxo de status, "assumir",
comentários, export e as regras de acesso (usuário comum só vê os próprios).

Marcador: tudo que estes testes criam tem título começando com "PYTEST" e é
removido no teardown — mantém o banco de teste limpo entre execuções.
"""
import pytest

from inventory.extensions import db
from inventory.models.ticket import Ticket
from inventory.models.user import User
from inventory.repositories import ticket_repo

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup_tickets(app):
    yield
    with app.app_context():
        for t in Ticket.query.filter(Ticket.title.like(f"{MARK}%")).all():
            db.session.delete(t)  # comentários caem por cascade
        db.session.commit()


def _admin_id(app, admin_email):
    with app.app_context():
        return User.query.filter_by(email=admin_email).first().id


def _common_id(app, common_email):
    with app.app_context():
        return User.query.filter_by(email=common_email).first().id


# --------------------------------------------------------------------------- #
# Repositório / regras de domínio
# --------------------------------------------------------------------------- #
def test_next_code_format(app):
    with app.app_context():
        code = ticket_repo.next_code()
        assert code.startswith("CH-") and code[3:].isdigit() and len(code) == 7


def test_create_ticket_sets_code_and_status(app, admin_email):
    aid = _admin_id(app, admin_email)
    with app.app_context():
        t = ticket_repo.create_ticket(opened_by_id=aid, title=f"{MARK} criação",
                                      category="software", priority="media",
                                      status="aberto")
        assert t.id and t.code.startswith("CH-")
        assert t.status == "aberto" and t.resolved_at is None


def test_status_resolved_sets_and_clears_resolved_at(app, admin_email):
    """Resolver carimba resolved_at; reabrir limpa (efeito colateral do repo)."""
    aid = _admin_id(app, admin_email)
    with app.app_context():
        t = ticket_repo.create_ticket(opened_by_id=aid, title=f"{MARK} status",
                                      category="outro", priority="baixa", status="aberto")
        ticket_repo.update_ticket(t, status="resolvido")
        assert t.resolved_at is not None
        ticket_repo.update_ticket(t, status="em_andamento")
        assert t.resolved_at is None


def test_add_comment_records_status_transition(app, admin_email):
    aid = _admin_id(app, admin_email)
    with app.app_context():
        t = ticket_repo.create_ticket(opened_by_id=aid, title=f"{MARK} coment",
                                      category="outro", priority="media", status="aberto")
        c = ticket_repo.add_comment(t, body="andamento 1", author_id=aid,
                                    new_status="em_andamento")
        assert t.status == "em_andamento"
        assert c.status_from == "aberto" and c.status_to == "em_andamento"
        # comentário sem mudança de status não registra transição
        c2 = ticket_repo.add_comment(t, body="andamento 2", author_id=aid)
        assert c2.status_from is None and c2.status_to is None
        assert len(t.comments) == 2


# --------------------------------------------------------------------------- #
# Rotas (admin)
# --------------------------------------------------------------------------- #
def test_admin_creates_ticket_via_form(app, auth_client):
    r = auth_client.post("/tickets/new", data={
        "title": f"{MARK} via form", "category": "hardware", "priority": "alta",
        "status": "aberto", "assigned_to_id": 0, "requester": "",
    }, follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        t = Ticket.query.filter_by(title=f"{MARK} via form").first()
        assert t is not None and t.priority == "alta"


def test_assume_assigns_and_advances(app, auth_client, admin_email):
    aid = _admin_id(app, admin_email)
    with app.app_context():
        t = ticket_repo.create_ticket(opened_by_id=aid, title=f"{MARK} assumir",
                                      category="outro", priority="media", status="aberto")
        tid = t.id
    r = auth_client.post(f"/tickets/{tid}/assumir", follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        t = db.session.get(Ticket, tid)
        assert t.assigned_to_id == aid and t.status == "em_andamento"


def test_admin_deletes_ticket(app, auth_client, admin_email):
    aid = _admin_id(app, admin_email)
    with app.app_context():
        t = ticket_repo.create_ticket(opened_by_id=aid, title=f"{MARK} del",
                                      category="outro", priority="media", status="aberto")
        tid = t.id
    r = auth_client.post(f"/tickets/{tid}/delete", follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        assert db.session.get(Ticket, tid) is None


# --------------------------------------------------------------------------- #
# Controle de acesso (usuário comum)
# --------------------------------------------------------------------------- #
def test_common_user_can_open_own_ticket(app, common_client):
    r = common_client.post("/tickets/new", data={
        "title": f"{MARK} comum abre", "category": "acesso", "priority": "media",
    }, follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        t = Ticket.query.filter_by(title=f"{MARK} comum abre").first()
        assert t is not None and t.status == "aberto"
        # solicitante e responsável foram forçados pelo servidor
        assert t.assigned_to_id is None


def test_common_user_blocked_from_others_ticket(app, common_client, admin_email):
    aid = _admin_id(app, admin_email)
    with app.app_context():
        t = ticket_repo.create_ticket(opened_by_id=aid, title=f"{MARK} do admin",
                                      category="outro", priority="media", status="aberto")
        tid = t.id
    assert common_client.get(f"/tickets/{tid}").status_code == 403


def test_common_user_cannot_edit_or_delete(app, common_client, common_email):
    """Mesmo nos próprios chamados, usuário comum não edita/exclui (só TI)."""
    cid = _common_id(app, common_email)
    with app.app_context():
        t = ticket_repo.create_ticket(opened_by_id=cid, title=f"{MARK} proprio",
                                      category="outro", priority="media", status="aberto")
        tid = t.id
    assert common_client.get(f"/tickets/{tid}/edit").status_code == 403
    assert common_client.post(f"/tickets/{tid}/delete").status_code == 403
    assert common_client.post(f"/tickets/{tid}/assumir").status_code == 403


def test_export_requires_admin(common_client):
    assert common_client.get("/tickets/export").status_code == 403
