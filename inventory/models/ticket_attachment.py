from ..extensions import db


class TicketAttachment(db.Model):
    """Arquivo anexado a um chamado (print, foto, PDF...)."""
    __tablename__ = "ticket_attachment"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    filename = db.Column(db.String(255), nullable=False)        # nome salvo em disco
    original_name = db.Column(db.String(255), nullable=True)    # nome original do arquivo
    content_type = db.Column(db.String(100), nullable=True)
    size = db.Column(db.Integer, nullable=True)                 # bytes
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    ticket = db.relationship(
        "Ticket",
        backref=db.backref("attachments", lazy=True, order_by="TicketAttachment.created_at",
                           cascade="all, delete-orphan"),
    )
    uploaded_by = db.relationship("User")

    @property
    def is_image(self) -> bool:
        return (self.content_type or "").startswith("image/")

    def __repr__(self) -> str:
        return f"<TicketAttachment {self.original_name!r} ticket={self.ticket_id}>"
