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
    # Aparelho compartilhado: até 2 funcionários adicionais usam o mesmo celular.
    assigned_employee_2 = db.Column(db.String(150), nullable=True, index=True)
    assigned_employee_3 = db.Column(db.String(150), nullable=True, index=True)
    sector = db.Column(db.String(120), nullable=True)          # setor
    patrimony = db.Column(db.String(60), nullable=True, index=True)

    # status: em_uso | disponivel | manutencao | inativo
    status = db.Column(db.String(15), nullable=False, default="em_uso",
                       server_default="em_uso", index=True)
    # Etiqueta QR já colada no aparelho (marcada pelo analista na tela de Etiquetas).
    label_applied = db.Column(db.Boolean, nullable=False, default=False,
                              server_default=db.text("false"))
    handed_at = db.Column(db.Date, nullable=True)              # data de entrega
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    @property
    def employees(self) -> list:
        """Funcionários vinculados ao aparelho, sem vazios e sem repetir o
        mesmo nome (a mesma pessoa nunca conta duas vezes)."""
        nomes = (self.assigned_employee, self.assigned_employee_2, self.assigned_employee_3)
        out, seen = [], set()
        for e in nomes:
            e = (e or "").strip()
            chave = e.lower()
            if e and chave not in seen:
                seen.add(chave)
                out.append(e)
        return out

    @property
    def is_shared(self) -> bool:
        return len(self.employees) > 1

    def __repr__(self) -> str:
        return f"<MobileDevice id={self.id} model={self.model!r} phone={self.phone_number!r}>"
