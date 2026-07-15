"""Controle local de tomadas/interruptores Tuya (NeoAvant) via tinytuya.

Fala direto com o dispositivo na LAN — sem nuvem e sem API oficial da NEO.
Requer device_id, IP e local_key (esta extraída uma vez pelo assistente da Tuya).
Tudo é best-effort: nunca levanta; retorna {ok: False, error: ...} em falha.
"""
from . import crypto

_TIMEOUT = 5  # segundos de espera pelo dispositivo (evita travar o request)


def _plain_key(plug) -> str:
    if not plug.local_key:
        return ""
    try:
        return crypto.decrypt(plug.local_key)
    except Exception:  # noqa: BLE001  (chave/VAULT_KEY inválida)
        return ""


def _device(plug):
    import tinytuya  # import tardio: só carrega quando realmente controla
    d = tinytuya.OutletDevice(plug.device_id, plug.ip_address, _plain_key(plug))
    try:
        d.set_version(float(plug.version or "3.3"))
    except (TypeError, ValueError):
        d.set_version(3.3)
    d.set_socketTimeout(_TIMEOUT)
    d.set_socketRetryLimit(1)
    return d


def _missing(plug) -> str:
    if not plug.ip_address:
        return "sem IP na rede"
    if not plug.local_key:
        return "sem local key"
    return ""


def get_status(plug) -> dict:
    """{ok, on, dps} do dispositivo, ou {ok:False, error}."""
    miss = _missing(plug)
    if miss:
        return {"ok": False, "error": miss}
    try:
        data = _device(plug).status()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    if not isinstance(data, dict) or "dps" not in data:
        err = data.get("Error") if isinstance(data, dict) else None
        return {"ok": False, "error": err or "sem resposta do dispositivo"}
    dp = str(plug.switch_dp or "1")
    return {"ok": True, "on": bool(data["dps"].get(dp)), "dps": data["dps"]}


def set_state(plug, on: bool) -> dict:
    """Liga/desliga o relé. {ok, on} ou {ok:False, error}."""
    miss = _missing(plug)
    if miss:
        return {"ok": False, "error": miss}
    dp = str(plug.switch_dp or "1")
    try:
        res = _device(plug).set_status(bool(on), switch=dp)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    if isinstance(res, dict) and res.get("Error"):
        return {"ok": False, "error": res.get("Error")}
    return {"ok": True, "on": bool(on)}
