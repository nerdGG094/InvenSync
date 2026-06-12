from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.license import License

_ALLOWED = {"name", "kind", "vendor", "license_key", "seats", "assigned_to",
            "start_date", "expiry_date", "cost", "notes"}


def list_licenses(search: Optional[str] = None, kind: Optional[str] = None) -> List[License]:
    query = License.query
    if kind:
        query = query.filter(License.kind == kind)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            License.name.ilike(s),
            License.vendor.ilike(s),
            License.assigned_to.ilike(s),
        ))
    return query.order_by(License.expiry_date.asc().nullslast(), License.name.asc()).all()


def expiring_within(days: int = 30) -> List[License]:
    """Licenças vencidas ou que vencem nos próximos `days` dias."""
    limit = date.today() + timedelta(days=days)
    return (License.query
            .filter(License.expiry_date.isnot(None), License.expiry_date <= limit)
            .order_by(License.expiry_date.asc()).all())


def get_license(lid: int) -> License:
    return License.query.get_or_404(lid)


def create_license(**kwargs) -> License:
    o = License(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(o)
    db.session.commit()
    return o


def update_license(o: License, **kwargs) -> License:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(o, k, kwargs[k])
    db.session.commit()
    return o


def delete_license(o: License) -> None:
    db.session.delete(o)
    db.session.commit()
