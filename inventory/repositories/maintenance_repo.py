from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models.machine_maintenance import MachineMaintenance
from ..models.machine import Machine

_ALLOWED = {"machine_id", "date", "kind", "description", "parts", "performed_by", "cost"}


def list_maintenances(search: Optional[str] = None,
                      machine_id: Optional[int] = None,
                      kind: Optional[str] = None) -> List[MachineMaintenance]:
    query = MachineMaintenance.query.options(joinedload(MachineMaintenance.machine))
    if machine_id:
        query = query.filter(MachineMaintenance.machine_id == machine_id)
    if kind:
        query = query.filter(MachineMaintenance.kind == kind)
    if search:
        s = f"%{search.strip()}%"
        query = query.join(Machine).filter(or_(
            MachineMaintenance.description.ilike(s),
            MachineMaintenance.parts.ilike(s),
            MachineMaintenance.performed_by.ilike(s),
            Machine.model.ilike(s),
            Machine.assigned_user.ilike(s),
            Machine.patrimony.ilike(s),
        ))
    return query.order_by(MachineMaintenance.date.desc(),
                          MachineMaintenance.id.desc()).all()


def get_maintenance(mid: int) -> MachineMaintenance:
    return MachineMaintenance.query.get_or_404(mid)


def create_maintenance(**kwargs) -> MachineMaintenance:
    m = MachineMaintenance(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(m)
    db.session.commit()
    return m


def update_maintenance(m: MachineMaintenance, **kwargs) -> MachineMaintenance:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(m, k, kwargs[k])
    db.session.commit()
    return m


def delete_maintenance(m: MachineMaintenance) -> None:
    db.session.delete(m)
    db.session.commit()
