from datetime import date

from ..extensions import db


class Domain(db.Model):
    """Domínio de internet registrado, vinculado a uma empresa do grupo."""
    __tablename__ = "domain"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False, index=True)   # ex.: bebidasjaboti.com.br
    company = db.Column(db.String(120), nullable=True, index=True)  # empresa do grupo
    # registrador: registro_br | godaddy | outro
    registrar = db.Column(db.String(20), nullable=False, default="registro_br",
                          server_default="registro_br", index=True)
    expiry_date = db.Column(db.Date, nullable=True, index=True)    # vencimento
    auto_renew = db.Column(db.Boolean, nullable=False, default=False,
                           server_default=db.false())
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    @property
    def days_left(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    @property
    def status(self) -> str:
        d = self.days_left
        if d is None:
            return "sem_data"
        if d < 0:
            return "vencido"
        if d <= 60:           # domínios pedem mais antecedência de renovação
            return "vencendo"
        return "vigente"

    def __repr__(self) -> str:
        return f"<Domain id={self.id} name={self.name!r} expiry={self.expiry_date}>"
