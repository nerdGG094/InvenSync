from ..extensions import db


class CredentialPhoto(db.Model):
    """Foto anexada a uma credencial do Cofre.

    Os arquivos ficam numa pasta PRIVADA (fora de static/) e são servidos só
    pela rota admin de /credentials — nunca por URL estática pública."""
    __tablename__ = "credential_photo"

    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"),
                              nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)        # nome salvo em disco
    original_name = db.Column(db.String(255), nullable=True)    # nome original enviado
    content_type = db.Column(db.String(100), nullable=True)
    size = db.Column(db.Integer, nullable=True)                 # bytes
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    credential = db.relationship(
        "Credential",
        backref=db.backref("photos", lazy=True,
                           order_by="CredentialPhoto.created_at",
                           cascade="all, delete-orphan"),
    )

    def __repr__(self) -> str:
        return f"<CredentialPhoto {self.original_name!r} cred={self.credential_id}>"
