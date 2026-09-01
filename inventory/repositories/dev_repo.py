from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import case, or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models.dev import DevChecklistItem, DevSprint, DevTask, DevUpdate

STATUSES = ["backlog", "todo", "doing", "review", "done"]

_TASK_FIELDS = {"title", "description", "status", "priority", "sprint_id",
                "assignee_id", "tags", "code_ref", "due_date", "ticket_id"}
_SPRINT_FIELDS = {"name", "goal", "start_date", "end_date", "status"}


# ----- Sprints -----
def list_sprints() -> List[DevSprint]:
    ordem = case((DevSprint.status == "ativa", 0), (DevSprint.status == "planejada", 1),
                 else_=2)
    return DevSprint.query.order_by(ordem, DevSprint.start_date.desc().nullslast(),
                                    DevSprint.id.desc()).all()


def active_sprints() -> List[DevSprint]:
    return DevSprint.query.filter(DevSprint.status != "concluida").order_by(
        DevSprint.name.asc()).all()


def get_sprint(sid: int) -> DevSprint:
    return db.get_or_404(DevSprint, sid)


def create_sprint(**kw) -> DevSprint:
    s = DevSprint(**{k: kw.get(k) for k in _SPRINT_FIELDS})
    db.session.add(s)
    db.session.commit()
    return s


def update_sprint(s: DevSprint, **kw) -> DevSprint:
    for k in _SPRINT_FIELDS:
        if k in kw:
            setattr(s, k, kw[k])
    db.session.commit()
    return s


def delete_sprint(s: DevSprint) -> None:
    db.session.delete(s)   # tasks.sprint_id -> NULL (SET NULL)
    db.session.commit()


# ----- Tasks -----
def get_task(tid: int) -> DevTask:
    return db.get_or_404(DevTask, tid)


def board(sprint_id=None, q=None, assignee_id=None, projeto=None,
          priority=None, atrasadas=False) -> dict:
    """{status: [tasks]} ordenado por position. sprint_id: int, 'backlog' (sem
    sprint) ou None (todas). Demais argumentos filtram o board."""
    query = DevTask.query
    if sprint_id == "backlog":
        query = query.filter(DevTask.sprint_id.is_(None))
    elif sprint_id:
        query = query.filter(DevTask.sprint_id == sprint_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(DevTask.title.ilike(like), DevTask.tags.ilike(like),
                                 DevTask.code_ref.ilike(like)))
    if assignee_id == "ninguem":
        query = query.filter(DevTask.assignee_id.is_(None))
    elif assignee_id:
        query = query.filter(DevTask.assignee_id == assignee_id)
    if projeto:
        # o projeto e a 1a tag; ilike casa em qualquer posicao da lista
        query = query.filter(DevTask.tags.ilike(f"%{projeto}%"))
    if priority:
        query = query.filter(DevTask.priority == priority)
    if atrasadas:
        query = query.filter(DevTask.due_date.isnot(None), DevTask.status != "done",
                             DevTask.due_date < datetime.now().date())
    # os cards mostram responsavel/criador (avatar) e sprint: carrega junto,
    # senao sao 3 consultas por card
    query = query.options(joinedload(DevTask.assignee), joinedload(DevTask.created_by),
                          joinedload(DevTask.sprint))
    tarefas = query.order_by(DevTask.position.asc(), DevTask.id.desc()).all()
    cols = {s: [] for s in STATUSES}
    for t in tarefas:
        cols.get(t.status, cols["backlog"]).append(t)
    return cols


def create_task(created_by_id=None, **kw) -> DevTask:
    data = {k: kw.get(k) for k in _TASK_FIELDS}
    # nova tarefa vai pro fim da coluna
    maxpos = (db.session.query(db.func.max(DevTask.position))
              .filter(DevTask.status == (data.get("status") or "backlog")).scalar()) or 0
    t = DevTask(created_by_id=created_by_id, position=maxpos + 1, **data)
    db.session.add(t)
    db.session.commit()
    return t


def update_task(t: DevTask, **kw) -> DevTask:
    for k in _TASK_FIELDS:
        if k in kw:
            setattr(t, k, kw[k])
    db.session.commit()
    return t


def move_task(t: DevTask, novo_status: str) -> DevTask:
    if novo_status in STATUSES and novo_status != t.status:
        maxpos = (db.session.query(db.func.max(DevTask.position))
                  .filter(DevTask.status == novo_status).scalar()) or 0
        t.status = novo_status
        t.position = maxpos + 1
        # done_at e o unico registro confiavel de "quando ficou pronto";
        # reabrir limpa, senao o burndown contaria a tarefa como entregue.
        t.done_at = datetime.now() if novo_status == "done" else None
        db.session.commit()
    return t


def reordenar(t: DevTask, ordem_ids: list) -> None:
    """Grava a nova ordem de uma coluna (arrastar para cima/baixo).

    Recebe os ids na ordem em que ficaram na tela; posicoes viram 1..N. So
    mexe em cards do mesmo status, para um id forjado nao remexer outra coluna.
    """
    ids = [int(i) for i in ordem_ids if str(i).isdigit()]
    if not ids:
        return
    tarefas = {x.id: x for x in DevTask.query.filter(DevTask.id.in_(ids),
                                                     DevTask.status == t.status).all()}
    for pos, tid in enumerate(ids, start=1):
        alvo = tarefas.get(tid)
        if alvo is not None:
            alvo.position = pos
    db.session.commit()


# ----- Checklist (subtarefas) -----
def add_checklist(t: DevTask, texto: str) -> DevChecklistItem:
    maxpos = (db.session.query(db.func.max(DevChecklistItem.position))
              .filter(DevChecklistItem.task_id == t.id).scalar()) or 0
    item = DevChecklistItem(task_id=t.id, text=texto[:200], position=maxpos + 1)
    db.session.add(item)
    db.session.commit()
    return item


def toggle_checklist(item: DevChecklistItem) -> DevChecklistItem:
    item.done = not item.done
    db.session.commit()
    return item


def get_checklist_item(cid: int) -> DevChecklistItem:
    return db.get_or_404(DevChecklistItem, cid)


def delete_checklist(item: DevChecklistItem) -> None:
    db.session.delete(item)
    db.session.commit()


def delete_task(t: DevTask) -> None:
    db.session.delete(t)   # updates somem via cascade
    db.session.commit()


def add_update(task: DevTask, user_id, body, code_ref=None) -> DevUpdate:
    u = DevUpdate(task_id=task.id, user_id=user_id, body=body, code_ref=code_ref)
    db.session.add(u)
    db.session.commit()
    return u


# ----- Dashboard -----
# Projetos que alimentam o board (a 1a tag dos cards criados pelo hook de
# commit). Lista explicita de proposito: sem ela, um card com tags "bug, dev"
# viraria um "projeto" chamado bug. Ao ligar um repo novo, acrescente aqui.
PROJETOS = ("invensync", "carreg-logi", "kiox")

STATUS_LABEL = {"backlog": "Backlog", "todo": "A fazer", "doing": "Fazendo",
                "review": "Revisão", "done": "Concluído"}
PRIORIDADE_LABEL = {"baixa": "Baixa", "media": "Média", "alta": "Alta",
                    "critica": "Crítica"}
PARADA_DIAS = 7


def _projeto_de(tags: str) -> str:
    itens = [t.strip().lower() for t in (tags or "").split(",") if t.strip()]
    for p in PROJETOS:
        if p in itens:
            return p
    return "sem projeto"


def estatisticas(dias: int = 30) -> dict:
    """Numeros e series do painel DEV, a partir dos lancamentos do board."""
    agora = datetime.now()
    desde = agora - timedelta(days=dias)

    por_status = dict(db.session.query(DevTask.status, db.func.count(DevTask.id))
                      .group_by(DevTask.status).all())
    por_prio = dict(db.session.query(DevTask.priority, db.func.count(DevTask.id))
                    .group_by(DevTask.priority).all())

    # Projeto sai da 1a tag: le so (id, tags), nao a tabela inteira
    projetos = {}
    for (tags,) in db.session.query(DevTask.tags).all():
        p = _projeto_de(tags)
        projetos[p] = projetos.get(p, 0) + 1

    # Atividade: atualizacoes (commits) por dia, com os dias vazios preenchidos
    brutos = dict(db.session.query(db.func.date(DevUpdate.created_at),
                                   db.func.count(DevUpdate.id))
                  .filter(DevUpdate.created_at >= desde)
                  .group_by(db.func.date(DevUpdate.created_at)).all())
    brutos = {(d.isoformat() if hasattr(d, "isoformat") else str(d)): n
              for d, n in brutos.items()}
    dias_serie, valores = [], []
    for i in range(dias - 1, -1, -1):
        d = (agora - timedelta(days=i)).date()
        dias_serie.append(d.strftime("%d/%m"))
        valores.append(brutos.get(d.isoformat(), 0))

    total = sum(por_status.values())
    concluidas = por_status.get("done", 0)
    andamento = por_status.get("doing", 0) + por_status.get("review", 0)
    fila = por_status.get("backlog", 0) + por_status.get("todo", 0)

    # Ciclo: criacao -> done_at (carimbado ao mover para Concluido).
    prontos = (DevTask.query.filter(DevTask.status == "done",
                                    DevTask.created_at.isnot(None),
                                    DevTask.done_at.isnot(None)).all())
    dias_medios = None
    if prontos:
        soma = sum(max((t.done_at - t.created_at).total_seconds(), 0) for t in prontos)
        dias_medios = round(soma / len(prontos) / 86400, 1)

    # Atrasadas: passou do prazo e nao terminou
    atrasadas = (DevTask.query
                 .filter(DevTask.due_date.isnot(None), DevTask.status != "done",
                         DevTask.due_date < agora.date())
                 .order_by(DevTask.due_date.asc()).all())
    # Vencendo nos proximos 7 dias (inclui hoje), sem contar as ja atrasadas
    vencendo = (DevTask.query
                .filter(DevTask.due_date.isnot(None), DevTask.status != "done",
                        DevTask.due_date >= agora.date(),
                        DevTask.due_date <= agora.date() + timedelta(days=7))
                .count())

    # Cards parados: em andamento e sem toque ha mais de PARADA_DIAS
    paradas = (DevTask.query
               .filter(DevTask.status.in_(("doing", "review")),
                       DevTask.updated_at < agora - timedelta(days=PARADA_DIAS))
               .order_by(DevTask.updated_at.asc()).limit(8).all())

    recentes = (DevUpdate.query.options(joinedload(DevUpdate.task),
                                        joinedload(DevUpdate.user))
                .order_by(DevUpdate.created_at.desc()).limit(10).all())

    sprint = DevSprint.query.filter_by(status="ativa").order_by(DevSprint.id.desc()).first()
    sprint_info = None
    if sprint:
        cont = dict(db.session.query(DevTask.status, db.func.count(DevTask.id))
                    .filter(DevTask.sprint_id == sprint.id)
                    .group_by(DevTask.status).all())
        tot_s = sum(cont.values())
        feitas = cont.get("done", 0)
        restam = None
        if sprint.end_date:
            restam = (sprint.end_date - agora.date()).days
        sprint_info = {"sprint": sprint, "total": tot_s, "feitas": feitas,
                       "pct": round(feitas * 100 / tot_s) if tot_s else 0,
                       "por_status": cont, "dias_restantes": restam,
                       "burndown": burndown(sprint)}

    def serie(d: dict, rotulos: dict, ordem=None):
        chaves = ordem or sorted(d, key=lambda k: -d[k])
        chaves = [k for k in chaves if d.get(k)]
        return {"labels": [rotulos.get(k, k) for k in chaves],
                "data": [d[k] for k in chaves],
                "chaves": chaves}

    return {
        "total": total, "concluidas": concluidas, "andamento": andamento, "fila": fila,
        "updates_periodo": sum(valores), "dias_medios": dias_medios, "dias": dias,
        "atrasadas": atrasadas, "vencendo": vencendo,
        "por_status": serie(por_status, STATUS_LABEL, list(STATUS_LABEL)),
        "por_prioridade": serie(por_prio, PRIORIDADE_LABEL, ["baixa", "media", "alta", "critica"]),
        "por_projeto": serie(projetos, {}),
        "atividade": {"labels": dias_serie, "data": valores},
        "paradas": paradas, "recentes": recentes, "sprint": sprint_info,
        "parada_dias": PARADA_DIAS,
    }


def burndown(sprint) -> dict:
    """Restante por dia da sprint: o que a equipe ainda devia, dia a dia.

    So e possivel porque `done_at` existe — `updated_at` muda a cada edicao e
    daria uma curva que sobe e desce sem relacao com entrega. A linha ideal e
    a reta do total ate zero, para comparar ritmo com prazo.
    """
    if not sprint or not sprint.start_date or not sprint.end_date:
        return {}
    tarefas = DevTask.query.filter(DevTask.sprint_id == sprint.id).all()
    total = len(tarefas)
    if not total:
        return {}
    fim = min(sprint.end_date, datetime.now().date())
    dias = (sprint.end_date - sprint.start_date).days
    # Sprint de um dia so (ou datas invertidas) nao tem curva: um ponto unico
    # desenharia a linha ideal em zero ao lado do restante real, sugerindo um
    # atraso que nao existe. Melhor nao mostrar grafico nenhum.
    if dias < 1:
        return {}
    labels, real, ideal = [], [], []
    for i in range(dias + 1):
        d = sprint.start_date + timedelta(days=i)
        labels.append(d.strftime("%d/%m"))
        ideal.append(round(total - total * i / dias, 2) if dias else 0)
        if d <= fim:
            feitas = sum(1 for t in tarefas
                         if t.done_at and t.done_at.date() <= d)
            real.append(total - feitas)
        else:
            real.append(None)      # futuro: a linha real simplesmente para
    return {"labels": labels, "real": real, "ideal": ideal, "total": total}
