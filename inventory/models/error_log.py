from ..extensions import db


class ErrorLog(db.Model):
    """Registro central de erros/exceções para diagnóstico em produção.

    Captura exceções não tratadas de requisições (via sinal) e falhas dos
    serviços de fundo que antes eram engolidas em silêncio.
    """
    __tablename__ = "error_log"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    level = db.Column(db.String(10), nullable=False, default="error",
                      server_default="error", index=True)      # error | warning
    source = db.Column(db.String(120), nullable=True, index=True)  # onde (ex.: 'request', 'monitoring')
    message = db.Column(db.String(500), nullable=True)
    traceback = db.Column(db.Text, nullable=True)
    path = db.Column(db.String(255), nullable=True)             # URL da requisição, se houver
    method = db.Column(db.String(10), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<ErrorLog {self.id} {self.level} {self.source!r}>"
