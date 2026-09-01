from typing import List, Optional

from sqlalchemy import case, or_

from ..extensions import db
from ..models.dev import DevSprint, DevTask, DevUpdate

STATUSES = ["backlog", "todo", "doing", "review", "done"]

_TASK_FIELDS = {"title", "description", "status", "priority", "sprint_id",
                "assignee_id", "tags", "code_ref"}
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


def board(sprint_id=None, q=None) -> dict:
    """{status: [tasks]} ordenado por position. sprint_id: int, 'backlog' (sem
    sprint) ou None (todas)."""
    query = DevTask.query
    if sprint_id == "backlog":
        query = query.filter(DevTask.sprint_id.is_(None))
    elif sprint_id:
        query = query.filter(DevTask.sprint_id == sprint_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(DevTask.title.ilike(like), DevTask.tags.ilike(like),
                                 DevTask.code_ref.ilike(like)))
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
        db.session.commit()
    return t


def delete_task(t: DevTask) -> None:
    db.session.delete(t)   # updates somem via cascade
    db.session.commit()


def add_update(task: DevTask, user_id, body, code_ref=None) -> DevUpdate:
    u = DevUpdate(task_id=task.id, user_id=user_id, body=body, code_ref=code_ref)
    db.session.add(u)
    db.session.commit()
    return u
