"""
Normalização FK — fase 1 (colunas/relacionamentos) e fase 2 (propagação de
rename + gravação da FK). Registros de teste têm prefixo PYTEST e são limpos.
"""
import pytest

from inventory.extensions import db
from inventory.models.user import User
from inventory.models.machine import Machine
from inventory.models.mobile import MobileDevice
from inventory.services import people

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        for M in (Machine, MobileDevice):
            for it in M.query.filter(M.model.like(f"{MARK}%")).all():
                db.session.delete(it)
        for u in User.query.filter(User.name.like(f"{MARK}%")).all():
            db.session.delete(u)
        db.session.commit()


def test_person_rename_propagates_to_assets(app):
    """Renomear uma pessoa atualiza o nome nos ativos que a referenciam por texto."""
    with app.app_context():
        db.session.add(User(name=f"{MARK} Fulano", is_active=True))
        m = Machine(model=f"{MARK}-PC", assigned_user=f"{MARK} Fulano")
        d = MobileDevice(model=f"{MARK}-Cel", assigned_employee=f"{MARK} Fulano")
        db.session.add_all([m, d])
        db.session.commit()
        mid, did = m.id, d.id

        people.propagate_person_rename(f"{MARK} Fulano", f"{MARK} Beltrano")
        db.session.commit()

        assert db.session.get(Machine, mid).assigned_user == f"{MARK} Beltrano"
        assert db.session.get(MobileDevice, did).assigned_employee == f"{MARK} Beltrano"


def test_department_rename_propagates_to_sectors(app):
    """Renomear um departamento atualiza o setor em Colaboradores e nos ativos."""
    with app.app_context():
        u = User(name=f"{MARK} Pessoa", sector=f"{MARK}SETOR", is_active=True)
        m = Machine(model=f"{MARK}-PC2", sector=f"{MARK}SETOR")
        db.session.add_all([u, m])
        db.session.commit()
        uid, mid = u.id, m.id

        people.propagate_sector_rename(f"{MARK}SETOR", f"{MARK}NOVO")
        db.session.commit()

        assert db.session.get(User, uid).sector == f"{MARK}NOVO"
        assert db.session.get(Machine, mid).sector == f"{MARK}NOVO"


def test_reconciliar_cria_pessoa_e_vincula(app, auth_client):
    """Órfão -> criar pessoa: cria o User e vincula o ativo (user_id)."""
    with app.app_context():
        m = Machine(model=f"{MARK}-orf", assigned_user=f"{MARK} Orfao")   # sem user_id
        db.session.add(m)
        db.session.commit()
        mid = m.id
    r = auth_client.post("/colaboradores/reconciliar",
                         data={"acao": "criar", "nome": f"{MARK} Orfao"}, follow_redirects=False)
    assert r.status_code in (301, 302, 303)
    with app.app_context():
        u = User.query.filter_by(name=f"{MARK} Orfao").first()
        assert u is not None
        assert db.session.get(Machine, mid).user_id == u.id


def test_reconciliar_vincula_existente(app, auth_client):
    """Órfão -> vincular a existente: aponta user_id e padroniza o nome."""
    with app.app_context():
        alvo = User(name=f"{MARK} Alvo", is_active=True)
        m = Machine(model=f"{MARK}-fonte", assigned_user=f"{MARK} Fonte")
        db.session.add_all([alvo, m])
        db.session.commit()
        aid, mid = alvo.id, m.id
    r = auth_client.post("/colaboradores/reconciliar",
                         data={"acao": "vincular", "nome": f"{MARK} Fonte", "user_id": aid},
                         follow_redirects=False)
    assert r.status_code in (301, 302, 303)
    with app.app_context():
        m = db.session.get(Machine, mid)
        assert m.user_id == aid and m.assigned_user == f"{MARK} Alvo"


def test_machine_write_populates_user_id(app, auth_client):
    """Salvar máquina pelo formulário preenche machine.user_id a partir do nome."""
    with app.app_context():
        u = User(name=f"{MARK} Dono", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id

    r = auth_client.post("/machines/new", data={
        "kind": "computador", "model": f"{MARK}-FK", "assigned_user": f"{MARK} Dono",
    }, follow_redirects=False)
    assert r.status_code in (301, 302)

    with app.app_context():
        m = Machine.query.filter_by(model=f"{MARK}-FK").first()
        assert m is not None and m.user_id == uid
        assert m.user.name == f"{MARK} Dono"   # relacionamento (fase 1) funcionando
