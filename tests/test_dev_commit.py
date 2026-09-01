"""Registro automatico de commits no board DEV (hook post-commit)."""
import pytest


def _purgar(app):
    """Apaga sobras de execucoes anteriores. Sem isso, um teste que quebrou no
    meio deixa o hash registrado e o proximo run cai em 'ja registrado'."""
    from inventory.extensions import db
    from inventory.models.dev import DevTask, DevUpdate
    from inventory.models.user import User
    with app.app_context():
        ids = [t.id for t in DevTask.query.filter(DevTask.title.like("%PYTEST%")).all()]
        if ids:
            DevUpdate.query.filter(DevUpdate.task_id.in_(ids)).delete(synchronize_session=False)
            DevTask.query.filter(DevTask.id.in_(ids)).delete(synchronize_session=False)
        User.query.filter(User.email.like("pytest-%@exemplo.com")).delete(
            synchronize_session=False)
        db.session.commit()


@pytest.fixture
def limpar(app):
    """Recolhe os ids criados no teste e apaga tudo no fim (updates antes)."""
    _purgar(app)
    criados = []
    yield criados
    from inventory.extensions import db
    from inventory.models.dev import DevTask, DevUpdate
    with app.app_context():
        for tid in criados:
            DevUpdate.query.filter_by(task_id=tid).delete()
            t = db.session.get(DevTask, tid)
            if t:
                db.session.delete(t)
        db.session.commit()


def test_commit_novo_cria_card_em_revisao(app, limpar):
    from inventory.services import dev_commit
    with app.app_context():
        r = dev_commit.registrar(
            mensagem="fix(dvr): PYTEST corrige o listener\n\nDetalhe do corpo.",
            hash_curto="aaa1111", arquivos=["inventory/services/dvr_events.py"],
            autor="Fulano <fulano@x.com>")
        assert r["acao"] == "criou"
        limpar.append(r["task_id"])

        from inventory.extensions import db
        from inventory.models.dev import DevTask, DevUpdate
        t = db.session.get(DevTask, r["task_id"])
        assert t.status == "review"
        assert t.priority == "alta"                  # fix -> alta
        assert t.tags == "fix, dvr"                  # tipo, escopo
        assert t.code_ref and "aaa1111" in t.code_ref
        u = DevUpdate.query.filter_by(task_id=t.id).one()
        assert "dvr_events.py" in u.body and "Fulano" in u.body


def test_mesmo_commit_nao_entra_duas_vezes(app, limpar):
    """O hook pode rodar de novo no mesmo hash — nao pode duplicar o card."""
    from inventory.services import dev_commit
    with app.app_context():
        r1 = dev_commit.registrar(mensagem="chore: PYTEST dedupe hash",
                                  hash_curto="bbb2222")
        limpar.append(r1["task_id"])
        r2 = dev_commit.registrar(mensagem="chore: PYTEST dedupe hash",
                                  hash_curto="bbb2222")
        assert r2["acao"] == "ignorado"


def test_amend_vira_atualizacao_do_mesmo_card(app, limpar):
    """`git commit --amend` roda o hook com outro hash e o mesmo titulo:
    tem que virar atualizacao, nao um card duplicado."""
    from inventory.services import dev_commit
    from inventory.models.dev import DevUpdate
    with app.app_context():
        r1 = dev_commit.registrar(mensagem="feat: PYTEST amend", hash_curto="ccc3333")
        limpar.append(r1["task_id"])
        r2 = dev_commit.registrar(mensagem="feat: PYTEST amend", hash_curto="ddd4444")
        assert r2["acao"] == "atualizou" and r2["task_id"] == r1["task_id"]
        assert DevUpdate.query.filter_by(task_id=r1["task_id"]).count() == 2


def test_commit_citando_id_atualiza_a_tarefa(app, limpar):
    from inventory.services import dev_commit
    from inventory.repositories import dev_repo
    from inventory.models.dev import DevUpdate
    with app.app_context():
        alvo = dev_repo.create_task(title="PYTEST tarefa alvo", status="doing")
        limpar.append(alvo.id)
        r = dev_commit.registrar(mensagem=f"fix: PYTEST ajuste #{alvo.id}",
                                 hash_curto="eee5555")
        assert r["acao"] == "atualizou" and r["task_id"] == alvo.id
        assert DevUpdate.query.filter_by(task_id=alvo.id).count() == 1


def test_merge_e_skip_kanban_sao_ignorados(app):
    _purgar(app)
    from inventory.services import dev_commit
    with app.app_context():
        assert dev_commit.registrar(
            mensagem="Merge branch 'main'", hash_curto="fff6666")["acao"] == "ignorado"
        assert dev_commit.registrar(
            mensagem="docs: nada a ver [skip-kanban]",
            hash_curto="9997777")["acao"] == "ignorado"


def test_card_fica_com_o_usuario_configurado(app, monkeypatch):
    """Os cards automaticos nascem no nome do usuario de DEV_COMMIT_USER_EMAIL."""
    _purgar(app)
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.models.user import User
    from inventory.services import dev_commit
    with app.app_context():
        dono = User(name="PYTEST Dono Commit", email="pytest-dono@exemplo.com")
        db.session.add(dono)
        db.session.commit()
        dono_id = dono.id
        monkeypatch.setenv("DEV_COMMIT_USER_EMAIL", "PYTEST-Dono@exemplo.com")  # case-insensitive
        r = dev_commit.registrar(mensagem="feat: PYTEST dono do card", hash_curto="111a8888")
        t = db.session.get(DevTask, r["task_id"])
        assert t.created_by_id == dono_id and t.assignee_id == dono_id
        # o card referencia o usuario: apaga na ordem (updates, card, usuario)
        from inventory.models.dev import DevUpdate
        DevUpdate.query.filter_by(task_id=t.id).delete()
        db.session.delete(t)
        db.session.commit()
        db.session.delete(db.session.get(User, dono_id))
        db.session.commit()


def test_dev_commit_py_nao_derruba_o_commit():
    """O script da raiz desliga os schedulers e nunca sai diferente de 0."""
    import pathlib
    fonte = pathlib.Path("dev_commit.py").read_text(encoding="utf-8")
    for var in ("MONITORING_ENABLED", "PRINTER_MONITOR_ENABLED", "DVR_EVENTS_ENABLED",
                "BACKUP_SCHEDULER_ENABLED"):
        assert var in fonte, f"{var} precisa ser desligado no script efemero"
    assert "sys.exit(0)" in fonte
