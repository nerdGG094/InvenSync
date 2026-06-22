from ..extensions import db


class Announcement(db.Model):
    """Aviso/recado da Central de Avisos.

    Mural interno: só administradores publicam; os demais usuários apenas
    visualizam. Para o perfil comum, a Central de Avisos é a tela inicial
    pós-login (no lugar do Painel, que continua sendo o destino do admin).
    """
    __tablename__ = "announcement"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)

    # Nível visual do aviso: info (azul), aviso (amarelo) ou urgente (vermelho).
    level = db.Column(db.String(15), nullable=False, default="info",
                      server_default="info")
    # Fixado aparece sempre no topo do mural.
    is_pinned = db.Column(db.Boolean, nullable=False, default=False,
                          server_default=db.text("false"))
    # Inativo some do mural (sem apagar o histórico).
    is_active = db.Column(db.Boolean, nullable=False, default=True,
                          server_default=db.text("true"), index=True)

    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(),
                           onupdate=db.func.now())

    author = db.relationship("User")

    def __repr__(self) -> str:
        return f"<Announcement id={self.id} title={self.title!r}>"
