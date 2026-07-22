from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.router import Router
from ..services import crypto

_ALLOWED = {
    "label", "brand", "model", "serial_number", "patrimony",
    "ip_address", "mac_address", "admin_user", "admin_password",
    "ssid", "wifi_password", "ssid_guest", "wifi_password_guest",
    "mac_filtering", "linked_macs", "location", "status", "notes", "label_applied",
}

# Segredos cifrados em repouso (VAULT_KEY). Ao editar, campo em branco = manter.
_SECRET_FIELDS = ("admin_password", "wifi_password", "wifi_password_guest")


def list_routers(search: Optional[str] = None, status: Optional[str] = None) -> List[Router]:
    query = Router.query
    if status:
        query = query.filter(Router.status == status)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            Router.label.ilike(s),
            Router.model.ilike(s),
            Router.brand.ilike(s),
            Router.ip_address.ilike(s),
            Router.ssid.ilike(s),
            Router.location.ilike(s),
            Router.patrimony.ilike(s),
        ))
    return query.order_by(Router.location.asc().nullslast(),
                          Router.label.asc().nullslast(),
                          Router.model.asc()).all()


def get_router(rid: int) -> Router:
    return db.get_or_404(Router, rid)


def create_router(**kwargs) -> Router:
    data = {k: kwargs.get(k) for k in _ALLOWED}
    for f in _SECRET_FIELDS:
        data[f] = crypto.encrypt(data.get(f)) or None
    r = Router(**data)
    db.session.add(r)
    db.session.commit()
    return r


def update_router(r: Router, **kwargs) -> Router:
    for k in _ALLOWED:
        if k in _SECRET_FIELDS:
            continue
        if k in kwargs:
            setattr(r, k, kwargs[k])
    # Senha em branco ao editar = manter a atual; se informada, cifra.
    for f in _SECRET_FIELDS:
        val = kwargs.get(f)
        if val:
            setattr(r, f, crypto.encrypt(val))
    db.session.commit()
    return r


def delete_router(r: Router) -> None:
    db.session.delete(r)
    db.session.commit()
