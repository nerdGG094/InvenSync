"""Módulo DEV: board, tarefas, mover, updates, sprints — admin-only."""


def test_dev_admin_only(app, auth_client, common_client):
    assert auth_client.get("/dev").status_code == 200
    assert common_client.get("/dev").status_code in (403, 302)


def test_criar_tarefa_aparece_no_board(app, auth_client):
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    r = auth_client.post("/dev/task/new", data={
        "title": "PYTEST tarefa board", "status": "todo", "priority": "alta",
        "sprint_id": "0", "assignee_id": "0", "tags": "bug, dev",
        "code_ref": "abc123"}, follow_redirects=True)
    assert r.status_code == 200
    b = auth_client.get("/dev").data
    assert "PYTEST tarefa board".encode() in b
    with app.app_context():
        t = DevTask.query.filter_by(title="PYTEST tarefa board").first()
        assert t and t.status == "todo" and t.priority == "alta"
        db.session.delete(t)
        db.session.commit()


def test_mover_tarefa_muda_status(app, auth_client):
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST mover", status="backlog")
        tid = t.id
    auth_client.post(f"/dev/task/{tid}/move", data={"status": "doing"})
    with app.app_context():
        assert db.session.get(DevTask, tid).status == "doing"
        db.session.delete(db.session.get(DevTask, tid))
        db.session.commit()


def test_update_registra_commit(app, auth_client):
    from inventory.extensions import db
    from inventory.models.dev import DevTask, DevUpdate
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST update", status="doing")
        tid = t.id
    auth_client.post(f"/dev/task/{tid}/update", data={
        "body": "ajustei o cache", "code_ref": "https://github.com/x/y/commit/deadbee"},
        follow_redirects=True)
    with app.app_context():
        ups = DevUpdate.query.filter_by(task_id=tid).all()
        assert len(ups) == 1 and "cache" in ups[0].body and ups[0].code_ref.endswith("deadbee")
        DevUpdate.query.filter_by(task_id=tid).delete()
        db.session.delete(db.session.get(DevTask, tid))
        db.session.commit()


def test_sprint_e_filtro_do_board(app, auth_client):
    from inventory.extensions import db
    from inventory.models.dev import DevTask, DevSprint
    from inventory.repositories import dev_repo
    with app.app_context():
        s = dev_repo.create_sprint(name="PYTEST Sprint 1", status="ativa")
        sid = s.id
        t1 = dev_repo.create_task(title="PYTEST na sprint", status="todo", sprint_id=sid)
        t2 = dev_repo.create_task(title="PYTEST no backlog", status="todo")
        t1id, t2id = t1.id, t2.id
    # filtrando pela sprint só mostra a tarefa da sprint
    b = auth_client.get(f"/dev?sprint={sid}").data
    assert b"PYTEST na sprint" in b and b"PYTEST no backlog" not in b
    # backlog (sem sprint)
    bb = auth_client.get("/dev?sprint=backlog").data
    assert b"PYTEST no backlog" in bb and b"PYTEST na sprint" not in bb
    with app.app_context():
        for i in (t1id, t2id):
            db.session.delete(db.session.get(DevTask, i))
        db.session.delete(db.session.get(DevSprint, sid))
        db.session.commit()


def test_board_cabe_na_tela_e_tem_botoes_de_mover(app, auth_client):
    """O board divide a largura entre as colunas (nada de scroll lateral) e cada
    card traz botoes de mover com icone."""
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST layout", status="doing")
        tid = t.id
    html = auth_client.get("/dev").data.decode("utf-8", "ignore")
    # colunas flexiveis, sem rolagem horizontal do board
    assert "overflow-x:auto" not in html.split(".dev-board{")[1].split("}")[0]
    assert "flex:1 1 0" in html
    # botoes de movimentacao no card (voltar / avancar / concluir)
    assert 'name="status" value="todo"' in html
    assert 'name="status" value="review"' in html
    assert 'name="status" value="done"' in html
    assert "bi-arrow-left" in html and "bi-arrow-right" in html
    with app.app_context():
        db.session.delete(db.session.get(DevTask, tid))
        db.session.commit()


def test_arrastar_card_responde_json(app, auth_client):
    """Arrastar-e-soltar move via fetch: o endpoint responde JSON (sem
    re-renderizar o board inteiro a cada card arrastado)."""
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.repositories import dev_repo
    with app.app_context():
        t = dev_repo.create_task(title="PYTEST arrastar", status="todo")
        tid = t.id
    r = auth_client.post(f"/dev/task/{tid}/move", data={"status": "review"},
                         headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.is_json
    assert r.get_json() == {"ok": True, "status": "review"}
    # o board precisa entregar os cards arrastaveis e as colunas como alvo
    html = auth_client.get("/dev").data.decode("utf-8", "ignore")
    assert 'draggable="true"' in html and 'data-drop="doing"' in html
    with app.app_context():
        assert db.session.get(DevTask, tid).status == "review"
        db.session.delete(db.session.get(DevTask, tid))
        db.session.commit()
