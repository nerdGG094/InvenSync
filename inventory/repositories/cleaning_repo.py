from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models.machine import Machine
from ..models.machine_cleaning import MachineCleaning

_ALLOWED = {
    "machine_id", "started_at", "finished_at", "executed_by",
    "period_days", "next_date", "notes",
}


def list_cleanings(search: Optional[str] = None,
                   machine_id: Optional[int] = None) -> List[MachineCleaning]:
    query = MachineCleaning.query.options(joinedload(MachineCleaning.machine))
    if machine_id:
        query = query.filter(MachineCleaning.machine_id == machine_id)
    if search:
        s = f"%{search.strip()}%"
        query = query.join(Machine).filter(or_(
            Machine.model.ilike(s),
            Machine.assigned_user.ilike(s),
            Machine.sector.ilike(s),
            Machine.ip_address.ilike(s),
            MachineCleaning.executed_by.ilike(s),
        ))
    return query.order_by(MachineCleaning.started_at.desc()).all()


def get_cleaning(cid: int) -> MachineCleaning:
    return MachineCleaning.query.get_or_404(cid)


def create_cleaning(**kwargs) -> MachineCleaning:
    c = MachineCleaning(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(c)
    db.session.commit()
    return c


def update_cleaning(c: MachineCleaning, **kwargs) -> MachineCleaning:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(c, k, kwargs[k])
    db.session.commit()
    return c


def delete_cleaning(c: MachineCleaning) -> None:
    db.session.delete(c)
    db.session.commit()
