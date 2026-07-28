from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.dvr import Dvr
from ..services import crypto

_ALLOWED = {
    "label", "brand", "model", "serial_number", "patrimony", "ip_address",
    "mac_address", "web_port", "admin_user", "admin_password", "channels",
    "location", "status", "notes",
}
_SECRET = ("admin_password",)   # cifrado em repouso; em branco ao editar = manter


def list_dvrs(search: Optional[str] = None, status: Optional[str] = None) -> List[Dvr]:
    query = Dvr.query
    if status:
        query = query.filter(Dvr.status == status)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            Dvr.label.ilike(s), Dvr.model.ilike(s), Dvr.brand.ilike(s),
            Dvr.ip_address.ilike(s), Dvr.location.ilike(s), Dvr.patrimony.ilike(s),
        ))
    return query.order_by(Dvr.location.asc().nullslast(),
                          Dvr.label.asc().nullslast(), Dvr.model.asc()).all()


def get_dvr(did: int) -> Dvr:
    return db.get_or_404(Dvr, did)


def create_dvr(**kwargs) -> Dvr:
    data = {k: kwargs.get(k) for k in _ALLOWED}
    for f in _SECRET:
        data[f] = crypto.encrypt(data.get(f)) or None
    d = Dvr(**data)
    db.session.add(d)
    db.session.commit()
    return d


def update_dvr(d: Dvr, **kwargs) -> Dvr:
    for k in _ALLOWED:
        if k in _SECRET:
            continue
        if k in kwargs:
            setattr(d, k, kwargs[k])
    for f in _SECRET:
        val = kwargs.get(f)
        if val:
            setattr(d, f, crypto.encrypt(val))
    db.session.commit()
    return d


def delete_dvr(d: Dvr) -> None:
    db.session.delete(d)
    db.session.commit()
