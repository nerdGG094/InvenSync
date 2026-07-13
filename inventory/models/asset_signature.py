from ..extensions import db


class AssetSignature(db.Model):
    """Assinatura do colaborador no Termo de Responsabilidade, guardada por nome
    (o termo é gerado por nome). Reaproveitada toda vez que o termo é reaberto."""
    __tablename__ = "asset_signature"

    id = db.Column(db.Integer, primary_key=True)
    person_key = db.Column(db.String(160), unique=True, index=True, nullable=False)  # nome normalizado
    person_name = db.Column(db.String(150), nullable=True)
    data_url = db.Column(db.Text, nullable=False)   # PNG em base64 (data:image/png;base64,...)
    signed_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __repr__(self) -> str:
        return f"<AssetSignature {self.person_name!r}>"
