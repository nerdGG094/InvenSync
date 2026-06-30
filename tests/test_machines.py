"""
Testes do módulo de Máquinas: CRUD via rota, busca do repositório, preenchimento
automático do setor a partir do cadastro do colaborador e o gate de acesso
(usuário comum é redirecionado — máquinas é área de admin).

Marcador: máquinas criadas têm model começando com "PYTEST"; pessoas de apoio,
nome começando com "PYTEST". Tudo é removido no teardown.
"""
import pytest

from inventory.extensions import db
from inventory.models.machine import Machine
from inventory.models.user import User
from inventory.repositories import machine_repo

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup_machines(app):
    yield
    with app.app_context():
        for m in Machine.query.filter(Machine.model.like(f"{MARK}%")).all():
            db.session.delete(m)
        for u in User.query.filter(User.name.like(f"{MARK}%")).all():
            db.session.delete(u)
        db.session.commit()


# --------------------------------------------------------------------------- #
# Repositório
# --------------------------------------------------------------------------- #
def test_create_and_get_machine(app):
    with app.app_context():
        m = machine_repo.create_machine(kind="notebook", model=f"{MARK} Dell 5420",
                                        assigned_user="Fulano", ip_address="10.0.0.9")
        got = machine_repo.get_machine(m.id)
        assert got.model == f"{MARK} Dell 5420" and got.kind == "notebook"


def test_search_matches_model_and_ip(app):
    with app.app_context():
        machine_repo.create_machine(kind="computador", model=f"{MARK} Optiplex",
                                    ip_address="192.168.5.5")
        assert any(r.model == f"{MARK} Optiplex"
                   for r in machine_repo.list_machines(search="Optiplex"))
        assert any(r.ip_address == "192.168.5.5"
                   for r in machine_repo.list_machines(search="192.168.5.5"))
        # filtro por tipo
        assert all(r.kind == "computador"
                   for r in machine_repo.list_machines(kind="computador"))


# --------------------------------------------------------------------------- #
# Rotas (admin)
# --------------------------------------------------------------------------- #
def test_admin_creates_machine_via_form(app, auth_client):
    r = auth_client.post("/machines/new", data={
        "kind": "computador", "model": f"{MARK} Form PC", "assigned_user": "",
        "sector": "TI", "is_active": "y",
    }, follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        assert Machine.query.filter_by(model=f"{MARK} Form PC").first() is not None


def test_sector_autofilled_from_person(app, auth_client):
    """Setor em branco + responsável cadastrado → herda o setor do colaborador."""
    with app.app_context():
        p = User(name=f"{MARK} Pessoa", sector="Logística", is_active=True)
        db.session.add(p)
        db.session.commit()
    r = auth_client.post("/machines/new", data={
        "kind": "notebook", "model": f"{MARK} Herdada",
        "assigned_user": f"{MARK} Pessoa", "sector": "",  # em branco de propósito
    }, follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        m = Machine.query.filter_by(model=f"{MARK} Herdada").first()
        assert m is not None and m.sector == "Logística"


def test_admin_edits_and_deletes_machine(app, auth_client):
    with app.app_context():
        m = machine_repo.create_machine(kind="computador", model=f"{MARK} Editar")
        mid = m.id
    r = auth_client.post(f"/machines/{mid}/edit", data={
        "kind": "computador", "model": f"{MARK} Editada", "assigned_user": "",
    }, follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        assert db.session.get(Machine, mid).model == f"{MARK} Editada"
    r = auth_client.post(f"/machines/{mid}/delete", follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        assert db.session.get(Machine, mid) is None


def test_history_page_loads(app, auth_client):
    with app.app_context():
        m = machine_repo.create_machine(kind="computador", model=f"{MARK} Hist")
        mid = m.id
    assert auth_client.get(f"/machines/{mid}/historico").status_code == 200


# --------------------------------------------------------------------------- #
# Controle de acesso
# --------------------------------------------------------------------------- #
def test_anonymous_redirected_to_login(client):
    r = client.get("/machines", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert "/login" in r.headers.get("Location", "")


def test_common_user_gated_out(common_client):
    """Usuário comum não acessa Máquinas — o gate global redireciona (302)."""
    r = common_client.get("/machines", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" not in r.headers.get("Location", "")  # vai p/ avisos, não login
