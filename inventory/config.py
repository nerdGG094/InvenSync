
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

    # Proteção CSRF (Flask-WTF). Token válido por toda a sessão — evita que
    # páginas abertas há muito tempo falhem ao enviar (comum em uso interno).
    WTF_CSRF_TIME_LIMIT = None

    # Logout automático por inatividade (minutos). 0 = desligado (padrão), para
    # não conflitar com o "lembrar-me". Defina INACTIVITY_MINUTES no .env p/ ligar.
    INACTIVITY_MINUTES = int(os.environ.get("INACTIVITY_MINUTES", "0"))

    # Cabeçalhos de segurança (CSP, X-Frame-Options, etc.). Desligue só p/ depurar.
    SECURITY_HEADERS = os.environ.get("SECURITY_HEADERS", "1") in ("1", "true", "True")

    # Exige 2FA dos administradores: admin sem 2FA é levado à configuração e só
    # navega depois de ativar. Desligue com FORCE_ADMIN_2FA=0 se precisar.
    FORCE_ADMIN_2FA = os.environ.get("FORCE_ADMIN_2FA", "1") in ("1", "true", "True")

    # Cofre: minutos que a re-autenticação (senha do próprio usuário) vale antes
    # de pedir de novo para revelar/copiar uma senha. 0 = pede toda vez.
    VAULT_REAUTH_MINUTES = int(os.environ.get("VAULT_REAUTH_MINUTES", "5"))

    # Bloqueio de conta após tentativas de senha erradas.
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))

    # Recarrega templates alterados sem precisar reiniciar o servidor
    # (conveniente mesmo rodando em produção via waitress).
    TEMPLATES_AUTO_RELOAD = True

    # Upload de fotos de perfil (avatares) e anexos de chamados
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    AVATAR_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "avatars")
    # Anexos de chamados e NFs contêm dados sensíveis — guardados FORA da pasta
    # estática (senão a rota pública /static burla o login/checagem de dono).
    # Servidos só por rotas autenticadas (tickets.attach_file / movements.nf).
    ATTACH_FOLDER = os.path.join(BASE_DIR, "uploads_private", "tickets")
    # Notas fiscais anexadas às entradas de estoque (XML/PDF)
    NF_FOLDER = os.path.join(BASE_DIR, "uploads_private", "nf")
    # Fotos das credenciais do Cofre — guardadas FORA da pasta estática (dados
    # sensíveis); servidas apenas pela rota admin de /credentials, nunca por URL
    # estática pública.
    CRED_PHOTO_FOLDER = os.path.join(BASE_DIR, "uploads_private", "credentials")

    # Backup automático do banco (agendador INTERNO; dispensa a Tarefa Agendada
    # externa do Windows). Gera 1 backup/dia a partir de BACKUP_HOUR, com self-heal.
    BACKUP_SCHEDULER_ENABLED = os.environ.get("BACKUP_SCHEDULER_ENABLED", "1") in ("1", "true", "True")
    BACKUP_HOUR = int(os.environ.get("BACKUP_HOUR", "2"))          # hora do dia (0-23)
    BACKUP_CHECK_SECONDS = int(os.environ.get("BACKUP_CHECK_SECONDS", "1800"))

    # Notificações por e-mail (SMTP) — desligado até MAIL_ENABLED=1.
    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "0") in ("1", "true", "True")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_TLS = os.environ.get("SMTP_TLS", "1") in ("1", "true", "True")
    MAIL_FROM = os.environ.get("MAIL_FROM", "")
    MAIL_TI = os.environ.get("MAIL_TI", "")  # destinatários da TI, separados por vírgula

    # Chave dedicada do cofre de senhas (Fernet). Se vazia, deriva do SECRET_KEY.
    VAULT_KEY = os.environ.get("VAULT_KEY", "")

    # Agendador das tomadas inteligentes (liga/desliga por horário).
    PLUG_SCHEDULER_ENABLED = os.environ.get("PLUG_SCHEDULER_ENABLED", "1") in ("1", "true", "True")
    # Aviso de tomada offline: de quanto em quanto tempo checar e a partir de
    # quantos minutos fora avisar a TI por e-mail.
    PLUG_OFFLINE_CHECK_MINUTES = int(os.environ.get("PLUG_OFFLINE_CHECK_MINUTES", "10"))
    PLUG_OFFLINE_ALERT_MINUTES = int(os.environ.get("PLUG_OFFLINE_ALERT_MINUTES", "30"))

    # Impressoras de rede via SNMP (páginas, toner, cilindro) — porta 161/UDP.
    SNMP_COMMUNITY = os.environ.get("SNMP_COMMUNITY", "public")
    SNMP_TIMEOUT = float(os.environ.get("SNMP_TIMEOUT", "3"))
    # Coleta periódica (histórico + alerta de suprimento baixo).
    PRINTER_MONITOR_ENABLED = os.environ.get("PRINTER_MONITOR_ENABLED", "1") in ("1", "true", "True")
    PRINTER_MONITOR_MINUTES = int(os.environ.get("PRINTER_MONITOR_MINUTES", "60"))
    PRINTER_SUPPLY_ALERT_PCT = int(os.environ.get("PRINTER_SUPPLY_ALERT_PCT", "10"))

    # Monitoramento de uptime (ping/HTTP em segundo plano).
    MONITORING_ENABLED = os.environ.get("MONITORING_ENABLED", "1") in ("1", "true", "True")
    MONITORING_INTERVAL = int(os.environ.get("MONITORING_INTERVAL", "120"))  # segundos

    # Alertas proativos (estoque mínimo, licenças/garantias vencendo, chamados parados).
    ALERTS_ENABLED = os.environ.get("ALERTS_ENABLED", "1") in ("1", "true", "True")
    ALERTS_TICKET_STUCK_HOURS = int(os.environ.get("ALERTS_TICKET_STUCK_HOURS", "48"))
    ALERTS_LICENSE_DAYS = int(os.environ.get("ALERTS_LICENSE_DAYS", "30"))
    # Digest por e-mail: horas do dia em que envia (no máximo 1x por janela/dia).
    # (aceita o nome antigo ALERTS_WHATSAPP_HOURS por compatibilidade.)
    ALERTS_DIGEST_HOURS = os.environ.get(
        "ALERTS_DIGEST_HOURS", os.environ.get("ALERTS_WHATSAPP_HOURS", "8,17"))
    # Frequência com que o agendador acorda para checar (minutos).
    ALERTS_CHECK_MINUTES = int(os.environ.get("ALERTS_CHECK_MINUTES", "30"))

    # Alertas de atividade suspeita na auditoria (e-mail à TI ao cruzar o limite
    # dentro de uma janela de ALERTS_CHECK_MINUTES).
    SECURITY_ALERTS_ENABLED = os.environ.get("SECURITY_ALERTS_ENABLED", "1") in ("1", "true", "True")
    SEC_ALERT_LOGINFAIL = int(os.environ.get("SEC_ALERT_LOGINFAIL", "15"))
    SEC_ALERT_REVEAL = int(os.environ.get("SEC_ALERT_REVEAL", "20"))
    SEC_ALERT_DELETE = int(os.environ.get("SEC_ALERT_DELETE", "25"))
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,   # evita conexões mortas após ociosidade
        "pool_recycle": 1800,    # recicla conexões a cada 30 min
    }

    SESSION_COOKIE_SAMESITE = "Lax"
    # Ative (SESSION_COOKIE_SECURE=1 no .env) ao servir por HTTPS atrás de proxy.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") in ("1", "true", "True")
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
