\
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
# Limite por IP de origem. Sem limites globais — só rotas decoradas (ex.: login).
# Armazenamento em memória: suficiente para o processo único do waitress.
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
