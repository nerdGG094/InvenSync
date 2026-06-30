from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.credential import Credential
from ..services import crypto

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
    data = {k: kwargs.get(k) for k in _ALLOWED}
    data["password"] = crypto.encrypt(data.get("password")) or None
    c = Credential(**data)
    db.session.add(c)
    db.session.commit()
    return c


def update_credential(c: Credential, **kwargs) -> Credential:
    for k in _ALLOWED:
        if k == "password":
            continue
        if k in kwargs:
            setattr(c, k, kwargs[k])
    # Senha em branco ao editar = manter a atual; se informada, cifra.
    pw = kwargs.get("password")
    if pw:
        c.password = crypto.encrypt(pw)
    db.session.commit()
    return c


def delete_credential(c: Credential) -> None:
    db.session.delete(c)
    db.session.commit()
