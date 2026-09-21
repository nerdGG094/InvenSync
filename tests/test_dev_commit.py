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


def test_skip_kanban_no_corpo_nao_ignora_o_commit(app, limpar):
    """Mensagem que EXPLICA o marcador no corpo nao pode ignorar a si mesma."""
    from inventory.services import dev_commit
    with app.app_context():
        r = dev_commit.registrar(
            mensagem="feat: PYTEST documenta a regra\n\nUse [skip-kanban] para pular.",
            hash_curto="222b9999")
        assert r["acao"] == "criou"
        limpar.append(r["task_id"])


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


def test_commit_de_rotina_nao_vira_card(app):
    """O CARREG-LOGI comita um backup automatico a cada 15 min: isso sozinho
    encheria o board de cards inuteis."""
    _purgar(app)
    from inventory.services import dev_commit
    with app.app_context():
        rotinas = ["Backup automatico 2026-09-01 10:05:09 PYTEST",
                   "backup automático 2026-09-01 10:20:09 PYTEST",
                   "WIP PYTEST ajustando o layout",
                   "auto-commit PYTEST do agendador"]
        # hash distinto por caso: com o mesmo hash, o dedupe mascararia a regra
        for i, assunto in enumerate(rotinas):
            r = dev_commit.registrar(mensagem=assunto, hash_curto=f"a1b2c{i}d")
            assert r["acao"] == "ignorado", assunto
        # controle: um commit normal com hash igual aos de cima passa
        ok = dev_commit.registrar(mensagem="feat: PYTEST controle da rotina",
                                  hash_curto="a1b2c9d")
        assert ok["acao"] == "criou"


def test_projeto_vira_primeira_tag(app, limpar):
    """O board recebe varios repositorios — o card precisa dizer de onde veio."""
    from inventory.extensions import db
    from inventory.models.dev import DevTask
    from inventory.services import dev_commit
    with app.app_context():
        r = dev_commit.registrar(mensagem="fix(menu): PYTEST vindo de outro repo",
                                 hash_curto="333c1111", projeto="CARREG-LOGI")
        limpar.append(r["task_id"])
        t = db.session.get(DevTask, r["task_id"])
        assert t.tags == "carreg-logi, fix, menu"


def test_mesmo_titulo_em_projetos_diferentes_nao_se_mistura(app, limpar):
    """Dois repos podem ter o mesmo assunto de commit sem ser o mesmo trabalho."""
    from inventory.services import dev_commit
    with app.app_context():
        a = dev_commit.registrar(mensagem="docs: PYTEST atualiza o CLAUDE.md",
                                 hash_curto="444d1111", projeto="invensync")
        b = dev_commit.registrar(mensagem="docs: PYTEST atualiza o CLAUDE.md",
                                 hash_curto="555e1111", projeto="carreg-logi")
        limpar.extend([a["task_id"], b["task_id"]])
        assert a["acao"] == "criou" and b["acao"] == "criou"
        assert a["task_id"] != b["task_id"]


def test_hook_serve_qualquer_repo(app):
    """O hook instalado em outro projeto chama o dev_commit.py do InvenSync."""
    import pathlib
    hook = pathlib.Path("setup/hooks/post-commit").read_text(encoding="utf-8")
    assert "@INVENSYNC@" in hook          # modelo: caminho entra na instalacao
    assert "--repo" in hook               # e o commit lido e o do repo local
    assert pathlib.Path("dev_commit.py").read_text(encoding="utf-8").count("--repo") >= 1


def _hook_em(repo, caminho_gravado):
    """Instala o modelo do hook num repo de teste, como o instalador faria."""
    import pathlib
    import subprocess
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    modelo = pathlib.Path("setup/hooks/post-commit").read_text(encoding="utf-8")
    alvo = repo / ".git" / "hooks" / "post-commit"
    alvo.write_text(modelo.replace("@INVENSYNC@", caminho_gravado), encoding="utf-8")
    alvo.chmod(0o755)
    return alvo


def _rodar(hook, repo, **ambiente):
    """Roda o hook isolado: HOME proprio, para nao ler a config da maquina."""
    import os
    import subprocess
    env = {k: v for k, v in os.environ.items()
           if k not in ("INVENSYNC_DIR", "INVENSYNC_PY")}
    env["HOME"] = str(repo.parent)
    env.update(ambiente)
    subprocess.run(["sh", str(hook)], cwd=str(repo), env=env, check=True)


@pytest.mark.skipif(__import__("os").name == "nt",
                    reason="o hook e um script sh; no Windows quem instala e o .ps1")
def test_hook_se_acha_com_caminho_de_outro_sistema(tmp_path):
    """Caminho de outro SO gravado na instalacao nao pode calar o hook.

    Aconteceu: o .git/hooks trazia C:/Users/... e, editando pelo Linux, o hook
    avisava no stderr e saia 0 — o commit passava e o card nunca nascia. Quando
    o commit e no proprio InvenSync, o dev_commit.py esta sempre a mao.
    """
    import os
    repo = tmp_path / "InventarioAlmox"
    repo.mkdir()
    (repo / "dev_commit.py").write_text("", encoding="utf-8")
    marca = tmp_path / "chamado.txt"
    interp = tmp_path / "python-falso"
    interp.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{marca}"\n', encoding="utf-8")
    interp.chmod(0o755)

    hook = _hook_em(repo, "C:/Users/Administrador/Desktop/python/INVENSYNC/InventarioAlmox")
    _rodar(hook, repo, INVENSYNC_PY=str(interp))

    chamada = marca.read_text(encoding="utf-8").splitlines()
    assert chamada[0] == str(repo / "dev_commit.py")
    assert "--repo" in chamada
    assert os.path.realpath(chamada[-1]) == os.path.realpath(str(repo))


@pytest.mark.skipif(__import__("os").name == "nt",
                    reason="o hook e um script sh; no Windows quem instala e o .ps1")
def test_hook_nao_escolhe_o_python_do_windows_no_linux(tmp_path):
    """Montado por SMB, o python.exe do Windows aparece como -rwx no Linux.

    Ou seja: [-x] nao distingue os dois mundos, e escolher por ele so falharia
    na hora do exec. Os candidatos tem que sair do uname.
    """
    repo = tmp_path / "InventarioAlmox"
    (repo / ".venv" / "Scripts").mkdir(parents=True)
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / "dev_commit.py").write_text("", encoding="utf-8")
    marca = tmp_path / "quem.txt"
    for nome, rotulo in ((".venv/Scripts/python.exe", "windows"), (".venv/bin/python", "linux")):
        alvo = repo / nome
        alvo.write_text(f'#!/bin/sh\necho {rotulo} > "{marca}"\n', encoding="utf-8")
        alvo.chmod(0o755)

    hook = _hook_em(repo, str(repo))
    _rodar(hook, repo)

    assert marca.read_text(encoding="utf-8").strip() == "linux"
