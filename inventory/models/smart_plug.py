from ..extensions import db


class SmartPlug(db.Model):
    """Tomada/interruptor inteligente Wi-Fi (Tuya / NeoAvant), controlada
    localmente na rede pelo protocolo Tuya (tinytuya) — sem nuvem e sem API.

    Precisa de device_id, IP na LAN e local_key (esta é cifrada em repouso com a
    VAULT_KEY, igual ao Cofre). A local_key é extraída uma única vez pelo
    assistente da Tuya (ver docs do módulo)."""
    __tablename__ = "smart_plug"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(120), nullable=True)      # setor / onde está
    device_id = db.Column(db.String(64), nullable=False)     # Tuya device id
    ip_address = db.Column(db.String(45), nullable=True)     # IP na LAN (fixar no roteador)
    local_key = db.Column(db.Text, nullable=True)            # cifrada (VAULT_KEY)
    version = db.Column(db.String(6), nullable=False, default="3.3", server_default="3.3")
    switch_dp = db.Column(db.String(8), nullable=False, default="1", server_default="1")  # DP do relé
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text("true"))
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<SmartPlug {self.name!r} {self.device_id!r}>"
