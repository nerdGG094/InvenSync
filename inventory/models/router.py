from ..extensions import db


class Router(db.Model):
    """Roteador/Access Point em uso na empresa, com credenciais de acesso."""
    __tablename__ = "router"

    id = db.Column(db.Integer, primary_key=True)

    label = db.Column(db.String(120), nullable=True)            # apelido/identificação interna
    brand = db.Column(db.String(80), nullable=True)             # marca (TP-Link, Intelbras...)
    model = db.Column(db.String(120), nullable=False)           # modelo do equipamento
    serial_number = db.Column(db.String(120), nullable=True)
    patrimony = db.Column(db.String(60), nullable=True, index=True)

    # Acesso administrativo ao roteador
    ip_address = db.Column(db.String(45), nullable=True, index=True)   # IP de gerência (admin)
    mac_address = db.Column(db.String(20), nullable=True)             # MAC do próprio roteador
    admin_user = db.Column(db.String(80), nullable=True)
    admin_password = db.Column(db.String(120), nullable=True)

    # Rede Wi-Fi
    ssid = db.Column(db.String(80), nullable=True, index=True)        # nome da rede principal
    wifi_password = db.Column(db.String(120), nullable=True)
    ssid_guest = db.Column(db.String(80), nullable=True)             # rede de visitantes (opcional)
    wifi_password_guest = db.Column(db.String(120), nullable=True)

    # Controle de acesso por MAC (vínculo dos telefones/dispositivos)
    mac_filtering = db.Column(db.Boolean, nullable=False, default=False,
                              server_default=db.false())
    linked_macs = db.Column(db.Text, nullable=True)                 # lista de MACs/aparelhos vinculados

    location = db.Column(db.String(150), nullable=True, index=True)  # local físico / setor

    # status: em_uso | disponivel | manutencao | inativo
    status = db.Column(db.String(15), nullable=False, default="em_uso",
                       server_default="em_uso", index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<Router id={self.id} model={self.model!r} ip={self.ip_address!r}>"
