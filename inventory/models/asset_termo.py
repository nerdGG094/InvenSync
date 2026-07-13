from ..extensions import db


class AssetTermo(db.Model):
    """Comprovante de entrega — congela os equipamentos e a assinatura no momento
    em que o Termo de Responsabilidade foi assinado. Serve de prova mesmo que o
    colaborador depois troque de máquina/celular."""
    __tablename__ = "asset_termo"

    id = db.Column(db.Integer, primary_key=True)
    person_key = db.Column(db.String(160), index=True, nullable=False)  # nome normalizado
    person_name = db.Column(db.String(150), nullable=True)
    sector = db.Column(db.String(120), nullable=True)
    equipamentos = db.Column(db.Text, nullable=True)   # JSON: lista de itens congelados
    signature = db.Column(db.Text, nullable=True)      # PNG data URL da assinatura na entrega
    signed_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)

    def __repr__(self) -> str:
        return f"<AssetTermo {self.person_name!r} @ {self.signed_at}>"
