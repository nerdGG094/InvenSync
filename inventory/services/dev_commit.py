"""Registra commits no board DEV — o kanban se alimenta do que a gente edita.

Chamado pelo hook `post-commit` (via `dev_commit.py` na raiz), tanto deste
repositorio quanto de outros (CARREG-LOGI, ...) — o board e de todos, e cada
card leva o nome do projeto como primeira tag. A regra:

* commit cuja mensagem cita ``#12``  -> vira **atualizacao** da tarefa 12;
* commit com titulo igual ao de um card recente (3 dias, fora de "Concluido")
  -> tambem vira atualizacao daquele card. E o caso do ``git commit --amend``,
  que roda o hook de novo com outro hash e sem isso criaria um card duplicado;
* qualquer outro commit -> **cria um card** em Revisao (``DEV_COMMIT_STATUS``),
  ja na sprint ativa, se houver.

Nada aqui pode derrubar um commit: quem chama trata excecao e sai com 0.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from ..extensions import db
from ..models.dev import DevSprint, DevTask, DevUpdate
from ..models.user import User

# Autor dos registros automaticos (Primo Spinelli). O commit pode ter sido
# feito por qualquer conta do git; no board o dono e sempre este usuario.
EMAIL_PADRAO = "ti@refrigerantesjaboti.com.br"

STATUS_PADRAO = "review"
DIAS_DEDUPE = 3

# tipo do conventional commit -> prioridade do card
_PRIORIDADE = {"fix": "alta", "hotfix": "critica", "revert": "alta",
               "feat": "media", "perf": "media", "refactor": "media",
               "docs": "baixa", "chore": "baixa", "test": "baixa", "style": "baixa"}

_RE_TAREFA = re.compile(r"#(\d+)")
_RE_CABECALHO = re.compile(r"^(?P<tipo>[a-z]+)(?:\((?P<escopo>[^)]+)\))?!?:\s*")
# Marcador que manda ignorar o commit. Procurado SO no assunto: uma mensagem
# que explica a regra no corpo ("[skip-kanban] ignora o commit") nao pode
# ignorar a si mesma — foi o que aconteceu no commit que criou este arquivo.
_RE_PULAR = re.compile(r"\[(skip[- ]kanban|no[- ]kanban)\]", re.I)
# Commits de rotina que nao sao "trabalho": o CARREG-LOGI comita um backup
# automatico a cada 15 min, o que sozinho encheria o board de cards inuteis.
# Sobrescrevivel por DEV_COMMIT_IGNORAR (regex, aplicada ao assunto).
IGNORAR_PADRAO = r"^(backup autom[aá]tico|wip\b|auto[- ]?commit)"


def _cfg(nome: str, padrao: str) -> str:
    return (os.environ.get(nome) or padrao).strip()


def _e_rotina(assunto: str) -> bool:
    """Commit automatico/rotineiro que nao merece card."""
    try:
        return bool(re.search(_cfg("DEV_COMMIT_IGNORAR", IGNORAR_PADRAO), assunto, re.I))
    except re.error:      # regex mal configurada no .env nao pode quebrar o hook
        return bool(re.search(IGNORAR_PADRAO, assunto, re.I))


def _usuario():
    """Usuario dono dos registros automaticos."""
    email = _cfg("DEV_COMMIT_USER_EMAIL", EMAIL_PADRAO).lower()
    return User.query.filter(db.func.lower(User.email) == email).first()


def _sprint_ativa():
    return DevSprint.query.filter_by(status="ativa").order_by(DevSprint.id.desc()).first()


def _ja_registrado(hash_curto: str) -> bool:
    if not hash_curto:
        return False
    alvo = f"%{hash_curto}%"
    if DevUpdate.query.filter(DevUpdate.code_ref.ilike(alvo)).first():
        return True
    return bool(DevTask.query.filter(DevTask.code_ref.ilike(alvo)).first())


def _card_recente(titulo: str, projeto: str = ""):
    """Card com o mesmo titulo, recente e ainda aberto (pega o --amend).

    Filtra pelo projeto: dois repositorios podem ter commits de mesmo titulo
    ("CLAUDE.md: ...") sem serem o mesmo trabalho."""
    limite = datetime.now() - timedelta(days=DIAS_DEDUPE)
    q = DevTask.query.filter(DevTask.title == titulo, DevTask.status != "done",
                             DevTask.created_at >= limite)
    if projeto:
        q = q.filter(DevTask.tags.ilike(f"%{projeto}%"))
    return q.order_by(DevTask.id.desc()).first()


def _partes(mensagem: str):
    linhas = (mensagem or "").strip().splitlines()
    assunto = (linhas[0] if linhas else "").strip()
    corpo = "\n".join(linhas[1:]).strip()
    return assunto, corpo


def _classificar(assunto: str, projeto: str = ""):
    """(prioridade, tags) a partir do cabecalho convencional `tipo(escopo):`.

    O projeto entra sempre como primeira tag — o board recebe varios repos."""
    m = _RE_CABECALHO.match(assunto or "")
    tipo = (m.group("tipo") or "").lower() if m else ""
    escopo = (m.group("escopo") or "").strip().lower() if m else ""
    tags = [t for t in (projeto.lower(), tipo, escopo) if t]
    return _PRIORIDADE.get(tipo, "media"), (", ".join(tags) or None)


def _texto_update(assunto: str, corpo: str, arquivos, autor: str | None) -> str:
    partes = [assunto]
    if corpo:
        partes.append(corpo)
    if arquivos:
        mostra = list(arquivos)[:12]
        lista = "\n".join(f"- {a}" for a in mostra)
        if len(arquivos) > len(mostra):
            lista += f"\n- (+{len(arquivos) - len(mostra)} arquivos)"
        partes.append(f"Arquivos ({len(arquivos)}):\n{lista}")
    if autor:
        partes.append(f"Commit por: {autor}")
    return "\n\n".join(p for p in partes if p)


def registrar(mensagem: str, hash_curto: str = "", url_commit: str = "",
              arquivos=None, autor: str = "", projeto: str = "") -> dict:
    """Joga um commit no board. Devolve o que foi feito (para o log do hook)."""
    assunto, corpo = _partes(mensagem)
    if not assunto:
        return {"acao": "ignorado", "motivo": "mensagem vazia"}
    if assunto.startswith("Merge ") or _RE_PULAR.search(assunto):
        return {"acao": "ignorado", "motivo": "merge ou [skip-kanban]"}
    if _e_rotina(assunto):
        return {"acao": "ignorado", "motivo": "commit de rotina (backup/wip)"}
    if _ja_registrado(hash_curto):
        return {"acao": "ignorado", "motivo": f"commit {hash_curto} ja registrado"}

    ref = (url_commit or hash_curto or "")[:300]
    usuario = _usuario()
    texto = _texto_update(assunto, corpo, arquivos or [], autor)

    # 1) commit citando #id -> atualizacao da tarefa existente
    tarefa = None
    m = _RE_TAREFA.search(mensagem or "")
    if m:
        tarefa = db.session.get(DevTask, int(m.group(1)))
    # 2) mesmo titulo, card recente e aberto -> foi um --amend/continuacao
    if tarefa is None:
        tarefa = _card_recente(assunto[:200], projeto)
    criado = False

    if tarefa is None:
        prioridade, tags = _classificar(assunto, projeto)
        sprint = _sprint_ativa()
        status = _cfg("DEV_COMMIT_STATUS", STATUS_PADRAO)
        if status not in ("backlog", "todo", "doing", "review", "done"):
            status = STATUS_PADRAO
        maxpos = (db.session.query(db.func.max(DevTask.position))
                  .filter(DevTask.status == status).scalar()) or 0
        tarefa = DevTask(
            title=assunto[:200], description=corpo or None,
            status=status, priority=prioridade,
            sprint_id=sprint.id if sprint else None,
            assignee_id=usuario.id if usuario else None,
            created_by_id=usuario.id if usuario else None,
            tags=tags, code_ref=ref or None, position=maxpos + 1)
        db.session.add(tarefa)
        db.session.flush()
        criado = True
    elif ref:
        tarefa.code_ref = ref      # o card aponta sempre para o commit mais novo

    db.session.add(DevUpdate(task_id=tarefa.id,
                             user_id=usuario.id if usuario else None,
                             body=texto, code_ref=ref or None))
    db.session.commit()
    return {"acao": "criou" if criado else "atualizou", "task_id": tarefa.id,
            "status": tarefa.status, "titulo": tarefa.title}
