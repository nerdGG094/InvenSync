from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.credential import Credential

_ALLOWED = {"name", "category", "url", "username", "password", "sector", "notes"}


def list_credentials(search: Optional[str] = None, category: Optional[str] = None) -> List[Credential]:
    query = Credential.query
    if category:
        query = query.filter(Credential.category == category)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            Credential.name.ilike(s),
            Credential.url.ilike(s),
            Credential.username.ilike(s),
            Credential.sector.ilike(s),
        ))
    return query.order_by(Credential.category.asc(), Credential.name.asc()).all()


def get_credential(cid: int) -> Credential:
    return Credential.query.get_or_404(cid)


def create_credential(**kwargs) -> Credential:
    c = Credential(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(c)
    db.session.commit()
    return c


def update_credential(c: Credential, **kwargs) -> Credential:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(c, k, kwargs[k])
    db.session.commit()
    return c


def delete_credential(c: Credential) -> None:
    db.session.delete(c)
    db.session.commit()
