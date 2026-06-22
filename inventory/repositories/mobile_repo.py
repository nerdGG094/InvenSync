from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.mobile import MobileDevice

_ALLOWED = {
    "brand", "model", "imei", "serial_number", "phone_number", "carrier",
    "plan", "assigned_employee", "assigned_employee_2", "assigned_employee_3",
    "sector", "patrimony", "status", "handed_at", "notes", "label_applied",
}


def list_mobiles(search: Optional[str] = None, status: Optional[str] = None) -> List[MobileDevice]:
    query = MobileDevice.query
    if status:
        query = query.filter(MobileDevice.status == status)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            MobileDevice.model.ilike(s),
            MobileDevice.brand.ilike(s),
            MobileDevice.phone_number.ilike(s),
            MobileDevice.imei.ilike(s),
            MobileDevice.assigned_employee.ilike(s),
            MobileDevice.assigned_employee_2.ilike(s),
            MobileDevice.assigned_employee_3.ilike(s),
            MobileDevice.sector.ilike(s),
            MobileDevice.patrimony.ilike(s),
        ))
    return query.order_by(MobileDevice.assigned_employee.asc().nullslast(),
                          MobileDevice.model.asc()).all()


def get_mobile(mid: int) -> MobileDevice:
    return MobileDevice.query.get_or_404(mid)


def create_mobile(**kwargs) -> MobileDevice:
    m = MobileDevice(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(m)
    db.session.commit()
    return m


def update_mobile(m: MobileDevice, **kwargs) -> MobileDevice:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(m, k, kwargs[k])
    db.session.commit()
    return m


def delete_mobile(m: MobileDevice) -> None:
    db.session.delete(m)
    db.session.commit()
