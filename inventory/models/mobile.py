from ..extensions import db


class MobileDevice(db.Model):
    """Celular fornecido pela empresa a um funcionário."""
    __tablename__ = "mobile_device"

    id = db.Column(db.Integer, primary_key=True)

    brand = db.Column(db.String(80), nullable=True)            # marca (Samsung, Motorola...)
    model = db.Column(db.String(120), nullable=False)          # modelo do aparelho
    imei = db.Column(db.String(40), nullable=True, index=True)
    serial_number = db.Column(db.String(120), nullable=True)
    phone_number = db.Column(db.String(30), nullable=True, index=True)   # linha/número
    carrier = db.Column(db.String(40), nullable=True)          # operadora
    plan = db.Column(db.String(80), nullable=True)             # plano/pacote

    assigned_employee = db.Column(db.String(150), nullable=True, index=True)  # funcionário
    sector = db.Column(db.String(120), nullable=True)          # setor
    patrimony = db.Column(db.String(60), nullable=True, index=True)

    # status: em_uso | disponivel | manutencao | inativo
    status = db.Column(db.String(15), nullable=False, default="em_uso",
                       server_default="em_uso", index=True)
    handed_at = db.Column(db.Date, nullable=True)              # data de entrega
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<MobileDevice id={self.id} model={self.model!r} phone={self.phone_number!r}>"
