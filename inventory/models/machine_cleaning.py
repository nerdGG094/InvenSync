from ..extensions import db


class MachineCleaning(db.Model):
    """Registro de limpeza/manutenção de uma máquina cadastrada."""
    __tablename__ = "machine_cleaning"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False, index=True)

    started_at = db.Column(db.DateTime, nullable=False)        # hora de início
    finished_at = db.Column(db.DateTime, nullable=True)        # hora de fim
    executed_by = db.Column(db.String(150), nullable=True)     # usuário de execução
    period_days = db.Column(db.Integer, nullable=True)         # periodicidade (dias)
    next_date = db.Column(db.Date, nullable=True, index=True)  # próxima limpeza
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    machine = db.relationship(
        "Machine",
        backref=db.backref("cleanings", lazy=True, cascade="all, delete-orphan"),
    )

    @property
    def duration_min(self):
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() // 60)
        return None

    def __repr__(self) -> str:
        return f"<MachineCleaning id={self.id} machine_id={self.machine_id} start={self.started_at}>"
