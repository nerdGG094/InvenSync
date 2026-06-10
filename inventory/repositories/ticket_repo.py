import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models.ticket import Ticket, TicketComment

_ALLOWED = {
    "title", "description", "requester", "sector", "category", "priority",
    "status", "assigned_to_id", "machine_id", "resolution",
}


def next_code() -> str:
    rows = Ticket.query.with_entities(Ticket.code).all()
    pat = re.compile(r"^CH-(\d+)$")
    mx = 0
    for (code,) in rows:
        m = pat.match(code or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return f"CH-{mx + 1:04d}"


def list_tickets(search: Optional[str] = None, status: Optional[str] = None,
                 priority: Optional[str] = None,
                 assigned_to_id: Optional[int] = None) -> List[Ticket]:
    query = Ticket.query.options(
        joinedload(Ticket.assigned_to), joinedload(Ticket.opened_by),
        joinedload(Ticket.machine),
    )
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            Ticket.code.ilike(s),
            Ticket.title.ilike(s),
            Ticket.requester.ilike(s),
            Ticket.sector.ilike(s),
            Ticket.description.ilike(s),
        ))
    if status:
        query = query.filter(Ticket.status == status)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if assigned_to_id:
        query = query.filter(Ticket.assigned_to_id == assigned_to_id)

    # Ordena: abertos/em andamento primeiro, depois por prioridade e data
    prio = {"urgente": 0, "alta": 1, "media": 2, "baixa": 3}
    tickets = query.all()
    open_rank = {"aberto": 0, "em_andamento": 1, "resolvido": 2, "cancelado": 3}
    tickets.sort(key=lambda t: (open_rank.get(t.status, 9),
                                prio.get(t.priority, 9),
                                -(t.id or 0)))
    return tickets


def get_ticket(tid: int) -> Ticket:
    return Ticket.query.options(
        joinedload(Ticket.comments).joinedload(TicketComment.author),
        joinedload(Ticket.assigned_to), joinedload(Ticket.opened_by),
        joinedload(Ticket.machine),
    ).filter_by(id=tid).first_or_404()


def _apply_status_side_effects(t: Ticket):
    if t.status == "resolvido" and t.resolved_at is None:
        t.resolved_at = datetime.now()
    if t.status not in ("resolvido",):
        t.resolved_at = None


def create_ticket(opened_by_id: Optional[int] = None, **kwargs) -> Ticket:
    data = {k: kwargs.get(k) for k in _ALLOWED}
    t = Ticket(code=next_code(), opened_by_id=opened_by_id, **data)
    _apply_status_side_effects(t)
    db.session.add(t)
    db.session.commit()
    return t


def update_ticket(t: Ticket, **kwargs) -> Ticket:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(t, k, kwargs[k])
    _apply_status_side_effects(t)
    db.session.commit()
    return t


def delete_ticket(t: Ticket) -> None:
    db.session.delete(t)
    db.session.commit()


def add_comment(t: Ticket, body: str, author_id: Optional[int] = None,
                new_status: Optional[str] = None) -> TicketComment:
    status_from = t.status
    status_to = None
    if new_status and new_status != t.status:
        status_to = new_status
        t.status = new_status
        _apply_status_side_effects(t)
    c = TicketComment(ticket=t, author_id=author_id, body=body,
                      status_from=status_from if status_to else None,
                      status_to=status_to)
    db.session.add(c)
    db.session.commit()
    return c
