from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.router import Router

_ALLOWED = {
    "label", "brand", "model", "serial_number", "patrimony",
    "ip_address", "mac_address", "admin_user", "admin_password",
    "ssid", "wifi_password", "ssid_guest", "wifi_password_guest",
    "mac_filtering", "linked_macs", "location", "status", "notes", "label_applied",
}


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
    return Router.query.get_or_404(rid)


def create_router(**kwargs) -> Router:
    r = Router(**{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(r)
    db.session.commit()
    return r


def update_router(r: Router, **kwargs) -> Router:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(r, k, kwargs[k])
    db.session.commit()
    return r


def delete_router(r: Router) -> None:
    db.session.delete(r)
    db.session.commit()
