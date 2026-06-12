"""
Registro de auditoria (best-effort): nunca quebra o fluxo do app.

Uso:
    from ..services import audit
    audit.record("delete", "ticket", t.id, f"Excluiu chamado {t.code}")
"""
from flask import request, has_request_context
from flask_login import current_user

from ..extensions import db
from ..models.audit import AuditLog


def record(action: str, entity: str = None, entity_id: int = None, summary: str = None) -> None:
    try:
        uid, uname = None, None
        try:
            if current_user and current_user.is_authenticated:
                uid = current_user.id
                uname = current_user.name
        except Exception:  # noqa: BLE001
            pass
        ip = request.remote_addr if has_request_context() else None
        log = AuditLog(user_id=uid, user_name=uname, action=action,
                       entity=entity, entity_id=entity_id,
                       summary=(summary or "")[:300], ip=ip)
        db.session.add(log)
        db.session.commit()
    except Exception:  # noqa: BLE001
        # Auditoria jamais derruba a operação principal.
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass


def list_logs(limit: int = 300, action: str = None, entity: str = None):
    q = AuditLog.query
    if action:
        q = q.filter(AuditLog.action == action)
    if entity:
        q = q.filter(AuditLog.entity == entity)
    return q.order_by(AuditLog.id.desc()).limit(limit).all()
