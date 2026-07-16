from ..extensions import db


class SmartPlugSchedule(db.Model):
    """Regra de agendamento de uma tomada: liga/desliga em um horário, em dias
    escolhidos da semana. Disparada pelo agendador em segundo plano do módulo."""
    __tablename__ = "smart_plug_schedule"

    id = db.Column(db.Integer, primary_key=True)
    plug_id = db.Column(db.Integer, db.ForeignKey("smart_plug.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    action = db.Column(db.String(4), nullable=False)   # "on" | "off"
    hour = db.Column(db.Integer, nullable=False)
    minute = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Dias da semana ISO (1=Seg ... 7=Dom) como string, ex.: "12345". Vazio = todos.
    days = db.Column(db.String(14), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text("true"))
    # Última janela (YYYYMMDDHHMM) em que já disparou — evita repetir no mesmo minuto.
    last_fired_slot = db.Column(db.String(12), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    plug = db.relationship(
        "SmartPlug",
        backref=db.backref("schedules", cascade="all, delete-orphan", lazy=True),
    )

    @property
    def hhmm(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    def matches_day(self, iso_weekday: int) -> bool:
        return (not self.days) or (str(iso_weekday) in self.days)

    def days_label(self) -> str:
        if not self.days or len(set(self.days)) >= 7:
            return "Todos os dias"
        nomes = {"1": "Seg", "2": "Ter", "3": "Qua", "4": "Qui", "5": "Sex", "6": "Sáb", "7": "Dom"}
        return ", ".join(nomes[d] for d in "1234567" if d in self.days)

    def __repr__(self) -> str:
        return f"<SmartPlugSchedule plug={self.plug_id} {self.action} {self.hhmm}>"
