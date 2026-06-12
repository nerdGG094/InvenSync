
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# Carrega variáveis sensíveis do arquivo .env (não versionado)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ---------------------------------------------------------------------------
# Banco de dados — PostgreSQL (instância PG17, porta 5432 deste servidor)
# Banco dedicado: inventario_almox
# Credenciais vêm do .env — veja .env.example para o modelo.
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "inventario_almox")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

# Permite sobrescrever a URL inteira via ambiente; caso contrário monta a do Postgres.
DATABASE_URL = os.environ.get("DATABASE_URL") or (
    f"postgresql+psycopg://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Recarrega templates alterados sem precisar reiniciar o servidor
    # (conveniente mesmo rodando em produção via waitress).
    TEMPLATES_AUTO_RELOAD = True

    # Upload de fotos de perfil (avatares) e anexos de chamados
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    AVATAR_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "avatars")
    ATTACH_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "tickets")

    # Notificações por WhatsApp (wppconnect-server) — desligado até configurar no .env
    WHATSAPP_ENABLED = os.environ.get("WHATSAPP_ENABLED", "0") in ("1", "true", "True")
    WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "")        # ex.: http://127.0.0.1:21465
    WHATSAPP_SESSION = os.environ.get("WHATSAPP_SESSION", "invensync")
    WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
    WHATSAPP_TI_NUMBERS = [s.strip() for s in os.environ.get("WHATSAPP_TI_NUMBERS", "").split(",") if s.strip()]
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,   # evita conexões mortas após ociosidade
        "pool_recycle": 1800,    # recicla conexões a cada 30 min
    }

    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
