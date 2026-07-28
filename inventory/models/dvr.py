from ..extensions import db


class Dvr(db.Model):
    """DVR/gravador de CFTV (câmeras) — equipamento de rede com painel de admin.
    Foco: inventário leve + status ao vivo + acesso ao painel (senha cifrada)."""
    __tablename__ = "dvr"

    id = db.Column(db.Integer, primary_key=True)

    label = db.Column(db.String(120), nullable=True)          # apelido/identificação
    brand = db.Column(db.String(80), nullable=True, default="Intelbras",
                      server_default="Intelbras")
    model = db.Column(db.String(120), nullable=False)
    serial_number = db.Column(db.String(120), nullable=True)
    patrimony = db.Column(db.String(60), nullable=True, index=True)

    # Acesso ao painel
    ip_address = db.Column(db.String(45), nullable=True, index=True)
    mac_address = db.Column(db.String(20), nullable=True, index=True)   # p/ status via ARP
    web_port = db.Column(db.Integer, nullable=True)           # porta do painel (padrão 80)
    admin_user = db.Column(db.String(80), nullable=True)
    admin_password = db.Column(db.String(255), nullable=True)  # cifrado (VAULT_KEY)

    channels = db.Column(db.Integer, nullable=True)          # nº de canais (opcional)
    location = db.Column(db.String(150), nullable=True, index=True)

    # status: em_uso | manutencao | inativo
    status = db.Column(db.String(15), nullable=False, default="em_uso",
                       server_default="em_uso", index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<Dvr id={self.id} model={self.model!r} ip={self.ip_address!r}>"
