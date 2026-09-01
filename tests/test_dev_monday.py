"""Recursos "estilo Monday" do board DEV: ordem, prazo, checklist, comentario,
filtros, vinculo com chamado, aviso por e-mail e burndown."""
from datetime import date, timedelta

import pytest


@pytest.fixture
def limpar(app):
    """Apaga as tarefas PYTEST no fim (e sobras de execucoes que quebraram)."""
    def purgar():
        from inventory.extensions import db
        from inventory.models.dev import DevChecklistItem, DevTask, DevUpdate
        with app.app_context():
            ids = [t.id for t in DevTask.query.filter(DevTask.title.like("%PYTEST%")).all()]
            if ids:
                DevUpdate.query.filter(DevUpdate.task_id.in_(ids)).delete(synchronize_session=False)
                DevChecklistItem.query.filter(DevChecklistItem.task_id.in_(ids)).delete(
                    synchronize_session=False)
                DevTask.query.filter(DevTask.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()
    purgar()
    yield
    purgar()


# ----- 1) Reordenar dentro da coluna -----
def test_reordenar_grava_a_ordem_da_coluna(app, auth_client, limpar):
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        a = dev_repo.create_task(title="PYTEST ordem A", status="todo")
        b = dev_repo.create_task(title="PYTEST ordem B", status="todo")
        c = dev_repo.create_task(title="PYTEST ordem C", status="todo")
        ids = [a.id, b.id, c.id]
    # sobe o C para o topo
    nova = [ids[2], ids[0], ids[1]]
    r = auth_client.post(f"/dev/task/{ids[0]}/reordenar",
                         data={"ordem": [str(i) for i in nova]},
                         headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    with app.app_context():
        pos = {i: db.session.get(DevTask, i).position for i in ids}
        assert pos[nova[0]] < pos[nova[1]] < pos[nova[2]]


def test_reordenar_nao_mexe_em_outra_coluna(app, auth_client, limpar):
    """Um id de outra coluna no payload nao pode remexer a posicao dela."""
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        a = dev_repo.create_task(title="PYTEST col A", status="todo")
        outro = dev_repo.create_task(title="PYTEST col outra", status="doing")
        outro.position = 99
        db.session.commit()
        aid, oid = a.id, outro.id
    auth_client.post(f"/dev/task/{aid}/reordenar", data={"ordem": [str(oid), str(aid)]})
    with app.app_context():
        assert db.session.get(DevTask, oid).position == 99


# ----- 2) Prazo e atrasadas -----
def test_prazo_marca_atrasada_e_filtra_no_board(app, auth_client, limpar):
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        velha = dev_repo.create_task(title="PYTEST venceu ontem", status="doing",
                                     due_date=date.today() - timedelta(days=1))
        futura = dev_repo.create_task(title="PYTEST vence depois", status="doing",
                                      due_date=date.today() + timedelta(days=3))
        pronta = dev_repo.create_task(title="PYTEST venceu mas feita", status="done",
                                      due_date=date.today() - timedelta(days=5))
        assert velha.atrasada is True
        assert futura.atrasada is False
        assert pronta.atrasada is False        # concluida nao esta atrasada
        st = dev_repo.estatisticas()
        assert velha.id in [t.id for t in st["atrasadas"]]
        assert st["vencendo"] >= 1
        db.session.expunge_all()
    b = auth_client.get("/dev/board?atrasadas=1").data
    assert b"PYTEST venceu ontem" in b and b"PYTEST vence depois" not in b


# ----- 3) Comentario rapido no card -----
def test_comentario_rapido_responde_json(app, auth_client, limpar):
    from inventory.models.dev import DevUpdate
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST comentar", status="doing")
        tid = t.id
    r = auth_client.post(f"/dev/task/{tid}/update", data={"body": "comentario do board"},
                         headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.is_json and r.get_json()["total"] == 1
    with app.app_context():
        u = DevUpdate.query.filter_by(task_id=tid).one()
        assert "comentario do board" in u.body
        DevUpdate.query.filter_by(task_id=tid).delete()
        from inventory.extensions import db
        db.session.commit()


# ----- 4) Checklist -----
def test_checklist_soma_percentual(app, auth_client, limpar):
    from inventory.extensions import db
    from inventory.models.dev import DevChecklistItem, DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST checklist", status="doing")
        tid = t.id
    auth_client.post(f"/dev/task/{tid}/checklist", data={"text": "primeiro item"})
    auth_client.post(f"/dev/task/{tid}/checklist", data={"text": "segundo item"})
    with app.app_context():
        t = db.session.get(DevTask, tid)
        assert t.checklist_total == 2 and t.checklist_pct == 0
        item = t.checklist.first()
        iid = item.id
    auth_client.post(f"/dev/checklist/{iid}/toggle")
    with app.app_context():
        t = db.session.get(DevTask, tid)
        assert t.checklist_feitos == 1 and t.checklist_pct == 50
    auth_client.post(f"/dev/checklist/{iid}/delete")
    with app.app_context():
        t = db.session.get(DevTask, tid)
        assert t.checklist_total == 1
        DevChecklistItem.query.filter_by(task_id=tid).delete()
        db.session.commit()


def test_checklist_some_junto_com_a_tarefa(app, limpar):
    """Cascade: apagar o card nao pode deixar itens orfaos."""
    from inventory.extensions import db
    from inventory.models.dev import DevChecklistItem
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST cascade")
        dev_repo.add_checklist(t, "item que deve sumir")
        tid = t.id
        dev_repo.delete_task(t)
        assert DevChecklistItem.query.filter_by(task_id=tid).count() == 0
        db.session.commit()


# ----- 5) Filtros do board -----
def test_filtros_do_board(app, auth_client, limpar):
    from inventory.extensions import db
    from inventory.models.user import User
    from inventory.repositories import dev_repo
    with app.app_context():
        dono = User(name="PYTEST Filtro Dono", email="pytest-filtro@exemplo.com")
        db.session.add(dono)
        db.session.commit()
        dono_id = dono.id
        dev_repo.create_task(title="PYTEST do fulano", status="todo",
                             assignee_id=dono_id, priority="critica", tags="kiox")
        dev_repo.create_task(title="PYTEST de ninguem", status="todo", priority="baixa",
                             tags="invensync")
    assert b"PYTEST do fulano" in auth_client.get(f"/dev/board?resp={dono_id}").data
    assert b"PYTEST de ninguem" not in auth_client.get(f"/dev/board?resp={dono_id}").data
    assert b"PYTEST de ninguem" in auth_client.get("/dev/board?resp=ninguem").data
    assert b"PYTEST do fulano" in auth_client.get("/dev/board?projeto=kiox").data
    assert b"PYTEST de ninguem" not in auth_client.get("/dev/board?projeto=kiox").data
    assert b"PYTEST do fulano" in auth_client.get("/dev/board?prio=critica").data
    assert b"PYTEST de ninguem" not in auth_client.get("/dev/board?prio=critica").data
    with app.app_context():
        from inventory.models.dev import DevTask
        DevTask.query.filter(DevTask.title.like("%PYTEST%")).delete(synchronize_session=False)
        db.session.commit()
        db.session.delete(db.session.get(User, dono_id))
        db.session.commit()


# ----- 6) Vinculo com chamado -----
def test_tarefa_vinculada_ao_chamado_aparece_dos_dois_lados(app, auth_client, limpar):
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.models.ticket import Ticket
    from inventory.repositories import dev_repo
    with app.app_context():
        ch = Ticket(title="PYTEST chamado origem", status="aberto")
        db.session.add(ch)
        db.session.commit()
        t = dev_repo.create_task(title="PYTEST tarefa do chamado", status="todo",
                                 ticket_id=ch.id)
        tid, cid = t.id, ch.id
        assert ch.dev_tasks.count() == 1        # lado do chamado
    # a pagina da tarefa mostra o chamado
    assert f"/tickets/{cid}".encode() in auth_client.get(f"/dev/task/{tid}").data
    # e a do chamado mostra a tarefa
    assert f"/dev/task/{tid}".encode() in auth_client.get(f"/tickets/{cid}").data
    with app.app_context():
        db.session.delete(db.session.get(DevTask, tid))
        db.session.commit()
        db.session.delete(db.session.get(Ticket, cid))
        db.session.commit()


# ----- 7) Aviso por e-mail ao atribuir -----
def test_avisa_por_email_quem_assumiu_a_tarefa(app, auth_client, limpar, monkeypatch):
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.models.user import User
    enviados = []
    monkeypatch.setattr("inventory.services.mailer.notify_user",
                        lambda u, s, b: enviados.append((u, s, b)))
    with app.app_context():
        outro = User(name="PYTEST Avisado", email="pytest-avisado@exemplo.com")
        db.session.add(outro)
        db.session.commit()
        oid = outro.id
    auth_client.post("/dev/task/new", data={
        "title": "PYTEST tarefa avisada", "status": "todo", "priority": "media",
        "sprint_id": "0", "assignee_id": str(oid), "ticket_id": "0"},
        follow_redirects=True)
    assert enviados, "deveria ter avisado o novo responsavel"
    assert "PYTEST tarefa avisada" in enviados[0][2]
    with app.app_context():
        DevTask.query.filter(DevTask.title.like("%PYTEST%")).delete(synchronize_session=False)
        db.session.commit()
        db.session.delete(db.session.get(User, oid))
        db.session.commit()


def test_nao_avisa_quem_se_atribuiu(app, auth_client, admin_email, limpar, monkeypatch):
    """Quem se colocou como responsavel nao precisa de e-mail."""
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.models.user import User
    enviados = []
    monkeypatch.setattr("inventory.services.mailer.notify_user",
                        lambda u, s, b: enviados.append(u))
    with app.app_context():
        # tem que ser O usuario logado no auth_client, nao "um admin qualquer"
        eu = User.query.filter(db.func.lower(User.email) == admin_email.lower()).one()
        meu_id = eu.id
    auth_client.post("/dev/task/new", data={
        "title": "PYTEST tarefa propria", "status": "todo", "priority": "media",
        "sprint_id": "0", "assignee_id": str(meu_id), "ticket_id": "0"},
        follow_redirects=True)
    assert not enviados
    with app.app_context():
        DevTask.query.filter(DevTask.title.like("%PYTEST%")).delete(synchronize_session=False)
        db.session.commit()


# ----- 8) done_at e burndown -----
def test_concluir_carimba_done_at_e_reabrir_limpa(app, limpar):
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST done_at", status="doing")
        dev_repo.move_task(t, "done")
        assert t.done_at is not None
        dev_repo.move_task(t, "doing")
        # reabrir tem que limpar, senao o burndown conta como entregue
        assert t.done_at is None
        db.session.delete(db.session.get(DevTask, t.id))
        db.session.commit()


def test_burndown_para_no_dia_de_hoje(app, limpar):
    """A linha real nao pode despencar ate zero no futuro e fingir que acabou."""
    from inventory.extensions import db
    from inventory.models.dev import DevSprint
    from inventory.repositories import dev_repo
    with app.app_context():
        s = dev_repo.create_sprint(name="PYTEST Sprint burndown", status="planejada",
                                   start_date=date.today() - timedelta(days=2),
                                   end_date=date.today() + timedelta(days=3))
        t1 = dev_repo.create_task(title="PYTEST bd 1", status="todo", sprint_id=s.id)
        t2 = dev_repo.create_task(title="PYTEST bd 2", status="todo", sprint_id=s.id)
        dev_repo.move_task(t1, "done")

        bd = dev_repo.burndown(s)
        assert bd["total"] == 2
        assert len(bd["labels"]) == 6                 # 2 dias atras .. 3 a frente
        assert bd["ideal"][0] == 2 and bd["ideal"][-1] == 0
        assert bd["real"][2] == 1                     # hoje: uma entregue
        assert bd["real"][-1] is None                 # futuro fica em branco

        for t in (t1, t2):
            db.session.delete(db.session.get(type(t), t.id))
        db.session.commit()
        db.session.delete(db.session.get(DevSprint, s.id))
        db.session.commit()


def test_burndown_nao_desenha_sprint_de_um_dia(app, limpar):
    """Um ponto so poria a linha ideal em zero ao lado do restante real e
    sugeriria um atraso inexistente."""
    from inventory.extensions import db
    from inventory.models.dev import DevSprint
    from inventory.repositories import dev_repo
    with app.app_context():
        s = dev_repo.create_sprint(name="PYTEST Sprint de um dia",
                                   start_date=date.today(), end_date=date.today())
        dev_repo.create_task(title="PYTEST um dia", sprint_id=s.id)
        assert dev_repo.burndown(s) == {}
        from inventory.models.dev import DevTask
        DevTask.query.filter(DevTask.title.like("%PYTEST%")).delete(synchronize_session=False)
        db.session.commit()
        db.session.delete(db.session.get(DevSprint, s.id))
        db.session.commit()
