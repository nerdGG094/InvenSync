from ..extensions import db


class MachineMaintenance(db.Model):
    """Registro de manutenção/reparo de uma máquina (peças, custo, o que foi feito)."""
    __tablename__ = "machine_maintenance"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False, index=True)

    date = db.Column(db.Date, nullable=False, index=True)        # data da manutenção
    # tipo: preventiva | corretiva | upgrade | formatacao | troca_peca | outro
    kind = db.Column(db.String(20), nullable=False, default="corretiva",
                     server_default="corretiva", index=True)
    description = db.Column(db.Text, nullable=False)            # o que foi feito
    parts = db.Column(db.Text, nullable=True)                   # peças trocadas/usadas
    performed_by = db.Column(db.String(150), nullable=True)     # quem executou (técnico/empresa)
    cost = db.Column(db.Numeric(10, 2), nullable=True)          # custo
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    machine = db.relationship(
        "Machine",
        backref=db.backref("maintenances", lazy=True, cascade="all, delete-orphan"),
    )

    def __repr__(self) -> str:
        return f"<MachineMaintenance id={self.id} machine_id={self.machine_id} date={self.date}>"
