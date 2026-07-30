"""Snapshot ao vivo das câmeras dos DVRs Intelbras/Dahua via CGI (Digest auth).

`http://IP[:porta]/cgi-bin/snapshot.cgi?channel=N` -> um JPEG do canal N.

A imagem é servida DE PASSAGEM (memória) — nada é gravado em disco. Um cache
curto por (dvr, canal) evita bater no DVR a cada refresh e compartilha a mesma
foto entre vários espectadores. Best-effort: falha -> devolve None.
"""
import ssl
import threading
import time
import urllib.error
import urllib.request

_CTX = ssl._create_unverified_context()
_openers = {}                 # did -> (opener, base_url)
_cache = {}                   # (did, ch) -> (ts, bytes)
_lock = threading.Lock()


def base_url(d) -> str:
    ip = (d.ip_address or "").strip()
    if not ip:
        return ""
    b = ip if "://" in ip else "http://" + ip
    if getattr(d, "web_port", None) and d.web_port != 80:
        b += f":{d.web_port}"
    return b


def _opener(d, pw):
    got = _openers.get(d.id)
    if got:
        return got
    b = base_url(d)
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, b, d.admin_user or "admin", pw or "")
    op = urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(mgr),
        urllib.request.HTTPBasicAuthHandler(mgr),
        urllib.request.HTTPSHandler(context=_CTX))
    _openers[d.id] = (op, b)
    return op, b


def _fetch(d, pw, ch, timeout):
    op, b = _opener(d, pw)
    r = op.open(f"{b}/cgi-bin/snapshot.cgi?channel={ch}", timeout=timeout)
    data = r.read(2_000_000)
    ctype = r.headers.get("Content-Type", "")
    if not ctype.startswith("image") or len(data) < 200:
        raise ValueError("resposta não-imagem")
    return data


def snapshot(d, pw, ch, ttl=5.0, timeout=8.0):
    """JPEG do canal `ch` (bytes) ou None. Usa cache de `ttl` segundos."""
    key = (d.id, int(ch))
    now = time.time()
    with _lock:
        c = _cache.get(key)
        if c and now - c[0] < ttl:
            return c[1]
    try:
        data = _fetch(d, pw, ch, timeout)
    except Exception:  # noqa: BLE001 — nonce expirou/erro: recria opener e tenta 1x
        _openers.pop(d.id, None)
        try:
            data = _fetch(d, pw, ch, timeout)
        except Exception:  # noqa: BLE001
            return None
    with _lock:
        _cache[key] = (now, data)
    return data
