from ..extensions import db


class AuditLog(db.Model):
    """Trilha de auditoria: quem fez o quê e quando (best-effort)."""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    user_name = db.Column(db.String(150), nullable=True)   # snapshot (caso o usuário seja removido)

    action = db.Column(db.String(30), nullable=False, index=True)   # create|update|delete|reveal|export|login
    entity = db.Column(db.String(40), nullable=True, index=True)    # ticket|router|credential|machine...
    entity_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(300), nullable=True)             # descrição legível
    ip = db.Column(db.String(45), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)

    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity}:{self.entity_id} by {self.user_name!r}>"
