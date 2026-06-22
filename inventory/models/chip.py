from ..extensions import db


class SimChip(db.Model):
    """Chip (linha/SIM) da empresa — controlado de forma independente do aparelho.

    Caso de uso central: a empresa entrega o chip para o funcionário usar no
    CELULAR PARTICULAR dele. Aqui o item controlado é a LINHA, não o aparelho.
    Quando o chip está num celular da empresa, ele se liga (opcionalmente) ao
    registro de Celular via `mobile_id`.
    """
    __tablename__ = "sim_chip"

    # usage: onde/como o chip está sendo usado (vale também como status)
    #   aparelho_empresa  -> dentro de um celular da empresa
    #   particular        -> no celular particular do funcionário
    #   disponivel        -> em estoque / sem uso
    #   cancelado         -> linha cancelada / inativa
    USAGE_LABELS = {
        "aparelho_empresa": "Aparelho da empresa",
        "particular": "Celular particular do funcionário",
        "disponivel": "Disponível / em estoque",
        "cancelado": "Cancelado / inativo",
    }

    id = db.Column(db.Integer, primary_key=True)

    phone_number = db.Column(db.String(30), nullable=False, index=True)  # número / linha
    carrier = db.Column(db.String(40), nullable=True)                    # operadora
    plan = db.Column(db.String(80), nullable=True)                       # plano / pacote
    iccid = db.Column(db.String(30), nullable=True, index=True)          # nº do chip (ICCID)

    assigned_employee = db.Column(db.String(150), nullable=True, index=True)  # responsável
    sector = db.Column(db.String(120), nullable=True)                    # setor

    usage = db.Column(db.String(20), nullable=False, default="particular",
                      server_default="particular", index=True)
    # Vínculo opcional ao celular da empresa onde o chip está instalado.
    mobile_id = db.Column(db.Integer, db.ForeignKey("mobile_device.id"), nullable=True)
    mobile = db.relationship("MobileDevice", lazy="joined")

    handed_at = db.Column(db.Date, nullable=True)                        # data de entrega
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    @property
    def usage_label(self) -> str:
        return self.USAGE_LABELS.get(self.usage, self.usage or "—")

    @property
    def is_personal(self) -> bool:
        return self.usage == "particular"

    def __repr__(self) -> str:
        return f"<SimChip id={self.id} phone={self.phone_number!r} usage={self.usage!r}>"
