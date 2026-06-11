
from ..extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=True)
    # Controle de acesso: usuários inativos não conseguem fazer login.
    # (sobrescreve a propriedade is_active do UserMixin do Flask-Login)
    is_active = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.text("true")
    )
    sector = db.Column(db.String(120), nullable=True)   # setor do usuário
    photo = db.Column(db.String(255), nullable=True)    # caminho da foto (avatar)

    @property
    def initials(self) -> str:
        return (self.name or "?")[:2].upper()

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
