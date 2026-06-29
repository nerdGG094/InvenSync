from datetime import datetime

from ..extensions import db


class Ticket(db.Model):
    """Chamado interno de TI — registrado pela equipe (não pelo solicitante)."""
    __tablename__ = "ticket"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, index=True)   # CH-0001

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    requester = db.Column(db.String(150), nullable=True)        # solicitante (pessoa/setor)
    sector = db.Column(db.String(120), nullable=True)

    category = db.Column(db.String(30), nullable=False, default="outro", server_default="outro")
    priority = db.Column(db.String(10), nullable=False, default="media", server_default="media")
    status = db.Column(db.String(15), nullable=False, default="aberto", server_default="aberto", index=True)

    opened_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)     # quem registrou
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)   # atendente
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=True)    # máquina relacionada

    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution = db.Column(db.Text, nullable=True)             # o que foi feito

    opened_by = db.relationship("User", foreign_keys=[opened_by_id])
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])
    machine = db.relationship("Machine")

    @property
    def is_open(self) -> bool:
        return self.status in ("aberto", "em_andamento")

    @property
    def age_hours(self):
        """Horas desde a abertura (até a resolução, se já resolvido)."""
        if not self.created_at:
            return None
        end = (self.resolved_at if (not self.is_open and self.resolved_at) else datetime.now())
        return (end - self.created_at).total_seconds() / 3600.0

    @property
    def age_label(self) -> str:
        h = self.age_hours
        if h is None:
            return ""
        if h < 1:
            return "agora há pouco"
        if h < 24:
            return f"{int(h)}h"
        return f"{int(h // 24)}d"

    def is_stuck(self, hours: int = 48) -> bool:
        """Chamado em aberto parado há mais de `hours` horas."""
        h = self.age_hours
        return bool(self.is_open and h is not None and h >= hours)

    def __repr__(self) -> str:
        return f"<Ticket {self.code} status={self.status!r} title={self.title!r}>"


class TicketComment(db.Model):
    """Andamento/atualização de um chamado (trilha de auditoria)."""
    __tablename__ = "ticket_comment"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    status_from = db.Column(db.String(15), nullable=True)
    status_to = db.Column(db.String(15), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    ticket = db.relationship(
        "Ticket",
        backref=db.backref("comments", lazy=True, order_by="TicketComment.created_at",
                           cascade="all, delete-orphan"),
    )
    author = db.relationship("User")
