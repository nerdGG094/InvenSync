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
