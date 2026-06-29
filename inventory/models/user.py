
import secrets

from ..extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


def _new_token() -> str:
    return secrets.token_hex(16)


class User(db.Model, UserMixin):
    """Cadastro central de pessoas (colaboradores) da empresa.

    Cada linha é uma pessoa. O login no sistema é OPCIONAL: só quem tem
    `can_login=True`, está ativo e possui senha consegue autenticar. Pessoas
    sem login servem apenas como "responsável" em Máquinas, Celulares,
    Chamados, Movimentações, etc.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    # E-mail é a identidade de login (quando há login). Opcional para quem só
    # é colaborador. Continua único — o Postgres permite vários NULL.
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False,
                         server_default=db.text("false"))
    # Tem acesso ao sistema (conta de login)? A maioria dos colaboradores não tem.
    can_login = db.Column(db.Boolean, nullable=False, default=False,
                          server_default=db.text("false"))
    # Controle de acesso: pessoas inativas não conseguem fazer login e não
    # aparecem como responsável nos formulários.
    # (sobrescreve a propriedade is_active do UserMixin do Flask-Login)
    is_active = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.text("true")
    )
    sector = db.Column(db.String(120), nullable=True)   # departamento / setor
    photo = db.Column(db.String(255), nullable=True)    # caminho da foto (avatar)
    whatsapp = db.Column(db.String(30), nullable=True)  # número p/ notificações

    # Token de sessão: ao rotacionar, invalida sessões/cookies "lembrar-me" em
    # outros dispositivos ("sair de todas as sessões").
    session_token = db.Column(db.String(32), nullable=True, default=_new_token)

    # Autenticação em dois fatores (TOTP / Google Authenticator)
    totp_secret = db.Column(db.String(64), nullable=True)
    is_2fa_enabled = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )

    def get_id(self) -> str:
        """ID para o Flask-Login no formato "id:token". Rotacionar o token
        invalida sessões e cookies "lembrar-me" emitidos antes (logout global)."""
        return f"{self.id}:{self.session_token or ''}"

    def rotate_session_token(self) -> None:
        self.session_token = _new_token()

    @property
    def initials(self) -> str:
        return (self.name or "?")[:2].upper()

    @property
    def can_authenticate(self) -> bool:
        """Pode fazer login? Precisa de conta de login ativa, com e-mail e senha."""
        return bool(self.can_login and self.is_active and self.email and self.password_hash)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
