"""
Serviço de notificação por WhatsApp via CallMeBot (gratuito, sem navegador/QR).

Como funciona o CallMeBot:
    Cada número de destino precisa de uma apikey própria. Para obtê-la, a pessoa
    envia UMA vez a mensagem "I allow callmebot to send me messages" para o número
    do CallMeBot (+34 644 51 95 23) e recebe a apikey de volta no WhatsApp.

    O envio é uma simples chamada HTTP GET:
        https://api.callmebot.com/whatsapp.php?phone=<55DDDXXXXXXXXX>&text=<msg>&apikey=<key>

Configuração (.env):
    WHATSAPP_ENABLED=1
    CALLMEBOT_RECIPIENTS=5544999999999:123456,5544988888888:654321
        (pares numero:apikey separados por vírgula — esses são os destinos da TI)

É tolerante a falhas: se o serviço estiver fora, NUNCA quebra o fluxo do app
(o chamado abre normalmente). Fica desligado até WHATSAPP_ENABLED=1 no .env.
"""
import re
import threading
import urllib.parse
import urllib.request

from flask import current_app

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


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


def _recipients() -> dict:
    """Mapa {numero_normalizado: apikey} a partir de CALLMEBOT_RECIPIENTS."""
    raw = current_app.config.get("CALLMEBOT_RECIPIENTS") or ""
    out = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        phone, _, key = pair.partition(":")
        phone = _normalize(phone)
        key = key.strip()
        if phone and key:
            out[phone] = key
    return out


def _send_raw(phone: str, apikey: str, text: str) -> bool:
    """Dispara uma mensagem via CallMeBot (GET). Retorna True em sucesso HTTP."""
    if not phone or not apikey:
        return False
    qs = urllib.parse.urlencode({"phone": phone, "text": text, "apikey": apikey})
    url = f"{CALLMEBOT_URL}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception as e:  # noqa: BLE001
        try:
            current_app.logger.warning("CallMeBot falhou para %s: %s", phone, e)
        except Exception:  # noqa: BLE001
            pass
        return False


def _dispatch(targets: dict, text: str):
    """Envia em background (não bloqueia a requisição que originou o alerta)."""
    if not _enabled() or not targets:
        return

    items = list(targets.items())

    def worker():
        for phone, apikey in items:
            try:
                _send_raw(phone, apikey, text)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=worker, daemon=True).start()


def notify_ti(text: str):
    """Notifica todos os destinos cadastrados da TI."""
    if not _enabled():
        return
    _dispatch(_recipients(), text)


def notify_user(user, text: str):
    """Notifica um usuário específico, se o WhatsApp dele tiver apikey cadastrada."""
    if not _enabled() or not user:
        return
    num = _normalize(getattr(user, "whatsapp", None))
    if not num:
        return
    apikey = _recipients().get(num)
    if apikey:
        _dispatch({num: apikey}, text)


def configured() -> bool:
    """True se houver ao menos um destino (numero:apikey) configurado."""
    return bool(_recipients())
