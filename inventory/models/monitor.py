from ..extensions import db


class MonitoredHost(db.Model):
    """Host monitorado por uptime (ping/HTTP): servidores, impressoras, roteadores, sites."""
    __tablename__ = "monitored_host"

    id = db.Column(db.Integer, primary_key=True)

    label = db.Column(db.String(120), nullable=False)          # nome amigável
    host = db.Column(db.String(255), nullable=False, index=True)  # IP, hostname ou URL
    # tipo: servidor | impressora | roteador | switch | site | outro
    kind = db.Column(db.String(20), nullable=False, default="servidor",
                     server_default="servidor", index=True)
    # forma de checagem: icmp (ping) | http (GET)
    check_type = db.Column(db.String(10), nullable=False, default="icmp",
                           server_default="icmp")

    enabled = db.Column(db.Boolean, nullable=False, default=True,
                        server_default=db.text("true"), index=True)

    # Estado da última verificação
    # last_status: up | down | unknown
    last_status = db.Column(db.String(10), nullable=False, default="unknown",
                            server_default="unknown", index=True)
    last_checked = db.Column(db.DateTime, nullable=True)
    last_latency_ms = db.Column(db.Integer, nullable=True)
    last_change = db.Column(db.DateTime, nullable=True)        # quando o status mudou
    fail_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    @property
    def is_up(self) -> bool:
        return self.last_status == "up"

    def __repr__(self) -> str:
        return f"<MonitoredHost id={self.id} host={self.host!r} status={self.last_status!r}>"
