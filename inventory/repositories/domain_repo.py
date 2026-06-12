from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.domain import Domain

_ALLOWED = {"name", "company", "registrar", "expiry_date", "auto_renew", "notes"}


def list_domains(search: Optional[str] = None, company: Optional[str] = None,
                 registrar: Optional[str] = None) -> List[Domain]:
    query = Domain.query
    if company:
        query = query.filter(Domain.company == company)
    if registrar:
        query = query.filter(Domain.registrar == registrar)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            Domain.name.ilike(s),
            Domain.company.ilike(s),
        ))
    return query.order_by(Domain.company.asc().nullslast(),
                          Domain.expiry_date.asc().nullslast(),
                          Domain.name.asc()).all()


def companies() -> List[str]:
    rows = (db.session.query(Domain.company)
            .filter(Domain.company.isnot(None))
            .distinct().order_by(Domain.company.asc()).all())
    return [r[0] for r in rows if r[0]]


def expiring_within(days: int = 60) -> List[Domain]:
    limit = date.today() + timedelta(days=days)
    return (Domain.query
            .filter(Domain.expiry_date.isnot(None), Domain.expiry_date <= limit)
            .order_by(Domain.expiry_date.asc()).all())


def get_domain(did: int) -> Domain:
    return Domain.query.get_or_404(did)


def create_domain(**kwargs) -> Domain:
    d = Domain(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(d)
    db.session.commit()
    return d


def update_domain(d: Domain, **kwargs) -> Domain:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(d, k, kwargs[k])
    db.session.commit()
    return d


def delete_domain(d: Domain) -> None:
    db.session.delete(d)
    db.session.commit()
