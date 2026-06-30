"""
Notificações por e-mail (SMTP) — tolerante a falhas e não-bloqueante.

Desligado até `MAIL_ENABLED=1` no .env. Configuração (ver .env.example):
    MAIL_ENABLED=1
    SMTP_HOST=smtp.empresa.com   SMTP_PORT=587   SMTP_TLS=1
    SMTP_USER=...   SMTP_PASSWORD=...
    MAIL_FROM="InvenSync <ti@empresa.com>"
    MAIL_TI=ti1@empresa.com,ti2@empresa.com   (destinatários da equipe de TI)

Espelha a API do serviço de WhatsApp: notify_ti / notify_user.
"""
import smtplib
import ssl
import threading
from email.message import EmailMessage

from flask import current_app


def _enabled() -> bool:
    return bool(current_app.config.get("MAIL_ENABLED"))


def _ti_recipients() -> list:
    raw = current_app.config.get("MAIL_TI") or ""
    return [e.strip() for e in raw.split(",") if e.strip()]


def configured() -> bool:
    return bool(current_app.config.get("SMTP_HOST") and _ti_recipients())


def _send_raw(to_list, subject, body) -> bool:
    host = current_app.config.get("SMTP_HOST")
    if not host or not to_list:
        return False
    port = int(current_app.config.get("SMTP_PORT", 587) or 587)
    user = current_app.config.get("SMTP_USER") or ""
    pwd = current_app.config.get("SMTP_PASSWORD") or ""
    sender = current_app.config.get("MAIL_FROM") or user or "invensync@localhost"
    use_tls = bool(current_app.config.get("SMTP_TLS", True))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ctx) as s:
                if user:
                    s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                if use_tls:
                    s.starttls(context=ctx)
                if user:
                    s.login(user, pwd)
                s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        try:
            current_app.logger.warning("SMTP falhou para %s: %s", to_list, e)
        except Exception:  # noqa: BLE001
            pass
        return False


def _dispatch(to_list, subject, body):
    if not _enabled() or not to_list:
        return
    app = current_app._get_current_object()

    def worker():
        with app.app_context():
            _send_raw(to_list, subject, body)

    threading.Thread(target=worker, daemon=True).start()


def notify_ti(subject, body):
    """Envia para os destinatários da equipe de TI (MAIL_TI)."""
    if not _enabled():
        return
    _dispatch(_ti_recipients(), subject, body)


def notify_user(user, subject, body):
    """Envia para o e-mail de um usuário específico, se houver."""
    if not _enabled() or not user:
        return
    to = (getattr(user, "email", None) or "").strip()
    if to:
        _dispatch([to], subject, body)
