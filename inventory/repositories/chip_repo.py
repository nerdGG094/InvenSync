from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.chip import SimChip

_ALLOWED = {
    "phone_number", "carrier", "plan", "iccid", "assigned_employee",
    "sector", "usage", "mobile_id", "handed_at", "notes",
}


def list_chips(search: Optional[str] = None, usage: Optional[str] = None) -> List[SimChip]:
    query = SimChip.query
    if usage:
        query = query.filter(SimChip.usage == usage)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            SimChip.phone_number.ilike(s),
            SimChip.carrier.ilike(s),
            SimChip.plan.ilike(s),
            SimChip.iccid.ilike(s),
            SimChip.assigned_employee.ilike(s),
            SimChip.sector.ilike(s),
        ))
    return query.order_by(SimChip.assigned_employee.asc().nullslast(),
                          SimChip.phone_number.asc()).all()


def get_chip(cid: int) -> SimChip:
    return SimChip.query.get_or_404(cid)


def create_chip(**kwargs) -> SimChip:
    c = SimChip(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(c)
    db.session.commit()
    return c


def update_chip(c: SimChip, **kwargs) -> SimChip:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(c, k, kwargs[k])
    db.session.commit()
    return c


def delete_chip(c: SimChip) -> None:
    db.session.delete(c)
    db.session.commit()
