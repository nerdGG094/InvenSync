"""
Serviço de notificação por WhatsApp (plugável, best-effort).

Pensado para o wppconnect-server (REST):
    POST {WHATSAPP_API_URL}/api/{WHATSAPP_SESSION}/send-message
    Authorization: Bearer {WHATSAPP_TOKEN}
    body: {"phone": "5511999999999", "message": "...", "isGroup": false}

É tolerante a falhas: se o WhatsApp estiver fora, NUNCA quebra o fluxo do app
(o chamado abre normalmente). Fica desligado até WHATSAPP_ENABLED=1 no .env.
"""
import json
import re
import urllib.request

from flask import current_app


def _digits(num: str) -> str:
    return re.sub(r"\D", "", num or "")


def _normalize(num: str) -> str:
    """Número BR para o formato 55DDDXXXXXXXXX (só dígitos)."""
    n = _digits(num)
    if not n:
        return ""
    if len(n) in (10, 11):   # DDD + número, sem país
        n = "55" + n
    return n


def _enabled() -> bool:
    return bool(current_app.config.get("WHATSAPP_ENABLED"))


def _send_one(target: str, text: str) -> bool:
    base = current_app.config.get("WHATSAPP_API_URL")
    session = current_app.config.get("WHATSAPP_SESSION")
    token = current_app.config.get("WHATSAPP_TOKEN")
    if not base or not session:
        return False

    is_group = str(target).endswith("@g.us")
    phone = target if is_group else _normalize(target)
    if not phone:
        return False

    url = f"{base.rstrip('/')}/api/{session}/send-message"
    body = json.dumps({"phone": phone, "message": text, "isGroup": is_group}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return 200 <= r.status < 300
    except Exception as e:  # noqa: BLE001
        current_app.logger.warning("WhatsApp falhou (%s): %s", target, e)
        return False


def _ti_targets() -> set:
    """Números da TI: lista do .env + WhatsApp de cada admin ativo."""
    targets = set(current_app.config.get("WHATSAPP_TI_NUMBERS") or [])
    try:
        from ..models.user import User
        for u in User.query.filter_by(is_admin=True, is_active=True).all():
            if getattr(u, "whatsapp", None):
                targets.add(u.whatsapp)
    except Exception:  # noqa: BLE001
        pass
    return {t for t in targets if t}


def notify_ti(text: str):
    if not _enabled():
        return
    for t in _ti_targets():
        try:
            _send_one(t, text)
        except Exception:  # noqa: BLE001
            pass


def notify_user(user, text: str):
    if not _enabled() or not user:
        return
    num = getattr(user, "whatsapp", None)
    if num:
        try:
            _send_one(num, text)
        except Exception:  # noqa: BLE001
            pass
