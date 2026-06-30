from ..extensions import db


class Credential(db.Model):
    """Credencial de TI guardada no cofre (servidor, e-mail, sistema, site...)."""
    __tablename__ = "credential"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False, index=True)   # identificação (ex.: "Servidor PG17")
    # categoria: servidor | email | sistema | site | banco | rede | outro
    category = db.Column(db.String(20), nullable=False, default="sistema",
                         server_default="sistema", index=True)
    url = db.Column(db.String(255), nullable=True)               # host/URL de acesso
    username = db.Column(db.String(150), nullable=True)
    # Guardada CIFRADA em repouso (Fernet); TEXT comporta o token. Ver services/crypto.py.
    password = db.Column(db.Text, nullable=True)
    sector = db.Column(db.String(120), nullable=True)            # setor/dono
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __repr__(self) -> str:
        return f"<Credential id={self.id} name={self.name!r} category={self.category!r}>"
