from ..extensions import db


class PrinterReading(db.Model):
    """Leitura SNMP de uma impressora num instante — histórico dos contadores.

    Coletada periodicamente pelo agendador. Guarda o total de páginas e os
    percentuais de toner/cilindro; a diferença entre leituras dá o consumo do
    período (páginas/mês por setor, etc.)."""
    __tablename__ = "printer_reading"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    taken_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    pages = db.Column(db.Integer, nullable=True)        # contador total de páginas
    toner_pct = db.Column(db.Integer, nullable=True)    # % de toner
    drum_pct = db.Column(db.Integer, nullable=True)     # % de cilindro (se houver)

    machine = db.relationship(
        "Machine",
        backref=db.backref("printer_readings", cascade="all, delete-orphan", lazy=True),
    )

    def __repr__(self) -> str:
        return f"<PrinterReading m={self.machine_id} pages={self.pages} @ {self.taken_at}>"
