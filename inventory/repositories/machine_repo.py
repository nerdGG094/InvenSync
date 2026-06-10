from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.machine import Machine

_ALLOWED = {
    "kind", "name", "brand", "model", "assigned_user", "ip_address",
    "sector", "patrimony", "serial_number", "notes", "is_active",
}


def list_machines(search: Optional[str] = None, kind: Optional[str] = None) -> List[Machine]:
    query = Machine.query
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            Machine.name.ilike(s),
            Machine.model.ilike(s),
            Machine.brand.ilike(s),
            Machine.assigned_user.ilike(s),
            Machine.ip_address.ilike(s),
            Machine.sector.ilike(s),
            Machine.patrimony.ilike(s),
            Machine.serial_number.ilike(s),
        ))
    if kind:
        query = query.filter(Machine.kind == kind)
    return query.order_by(Machine.assigned_user.asc().nullslast(),
                          Machine.model.asc()).all()


def get_machine(mid: int) -> Machine:
    return Machine.query.get_or_404(mid)


def create_machine(**kwargs) -> Machine:
    m = Machine(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(m)
    db.session.commit()
    return m


def update_machine(m: Machine, **kwargs) -> Machine:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(m, k, kwargs[k])
    db.session.commit()
    return m


def delete_machine(m: Machine) -> None:
    db.session.delete(m)
    db.session.commit()
