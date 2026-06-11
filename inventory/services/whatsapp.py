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
import threading
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


def _send_raw(base, session, token, target: str, text: str) -> bool:
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
    except Exception:  # noqa: BLE001
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


def _dispatch(targets, text: str):
    """Envia em background (não bloqueia a requisição do chamado)."""
    if not _enabled():
        return
    base = current_app.config.get("WHATSAPP_API_URL")
    session = current_app.config.get("WHATSAPP_SESSION")
    token = current_app.config.get("WHATSAPP_TOKEN")
    nums = [t for t in targets if t]
    if not nums:
        return

    def worker():
        for t in nums:
            try:
                _send_raw(base, session, token, t, text)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=worker, daemon=True).start()


def notify_ti(text: str):
    if not _enabled():
        return
    _dispatch(_ti_targets(), text)


def notify_user(user, text: str):
    if not _enabled() or not user:
        return
    num = getattr(user, "whatsapp", None)
    if num:
        _dispatch([num], text)


# ===== Sessão / conexão (usado pela página de QR no app) =====
def _api(path: str, method: str = "GET", body: dict = None, timeout: int = 20):
    base = current_app.config.get("WHATSAPP_API_URL")
    session = current_app.config.get("WHATSAPP_SESSION")
    token = current_app.config.get("WHATSAPP_TOKEN")
    if not base or not session:
        return None
    url = f"{base.rstrip('/')}/api/{session}/{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        current_app.logger.warning("WhatsApp API %s falhou: %s", path, e)
        return None


def status():
    """Status da sessão (+ qrcode quando estiver aguardando leitura)."""
    return _api("status-session") or {"status": "OFFLINE", "qrcode": None}


def start():
    """Inicia a sessão e retorna o QR (waitQrCode aguarda o QR ser gerado)."""
    return _api("start-session", "POST", {"webhook": "", "waitQrCode": True}, timeout=40)


def configured() -> bool:
    return bool(current_app.config.get("WHATSAPP_API_URL")
                and current_app.config.get("WHATSAPP_TOKEN"))
