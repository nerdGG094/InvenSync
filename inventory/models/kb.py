from ..extensions import db


class KbArticle(db.Model):
    """Artigo da base de conhecimento (FAQ/solução de problema recorrente)."""
    __tablename__ = "kb_article"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False, index=True)
    # categoria alinhada às de chamados: hardware|software|rede|impressora|acesso|outro
    category = db.Column(db.String(30), nullable=False, default="outro",
                         server_default="outro", index=True)
    problem = db.Column(db.Text, nullable=True)         # sintoma / pergunta
    solution = db.Column(db.Text, nullable=False)       # solução / resposta
    tags = db.Column(db.String(255), nullable=True)     # palavras-chave separadas por vírgula
    views = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    created_by = db.relationship("User")

    def __repr__(self) -> str:
        return f"<KbArticle id={self.id} title={self.title!r}>"
