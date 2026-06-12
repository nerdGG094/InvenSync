from datetime import date

from ..extensions import db


class License(db.Model):
    """Licença de software, garantia ou contrato com data de vencimento."""
    __tablename__ = "license"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False, index=True)   # ex.: "Windows 11 Pro"
    # tipo: licenca | garantia | contrato | certificado | outro
    kind = db.Column(db.String(20), nullable=False, default="licenca",
                     server_default="licenca", index=True)
    vendor = db.Column(db.String(120), nullable=True)            # fornecedor/fabricante
    license_key = db.Column(db.String(255), nullable=True)       # chave/serial
    seats = db.Column(db.Integer, nullable=True)                 # qtd de licenças
    assigned_to = db.Column(db.String(150), nullable=True)       # máquina/setor/responsável

    start_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True, index=True)  # vencimento
    cost = db.Column(db.Numeric(10, 2), nullable=True)
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
        if d <= 30:
            return "vencendo"
        return "vigente"

    def __repr__(self) -> str:
        return f"<License id={self.id} name={self.name!r} expiry={self.expiry_date}>"
