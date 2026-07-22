"""Controle/checagem dos roteadores para o painel do admin.

Descobre, ao vivo e SEM enviar credenciais na sondagem de estado:
  - se o painel de administração está online + latência;
  - COMO ele autentica (Basic Auth vs formulário) — o que decide se o
    "Entrar direto" (auto-login por URL) é possível.

Regra prática (confirmada nos equipamentos da empresa):
  - Basic Auth (popup do navegador)  -> `http://user:senha@IP` entra logado.
  - Formulário (campos na página)     -> o navegador NÃO deixa outro site
    preencher o login; o máximo é abrir a página e copiar a senha.

Tudo best-effort: nunca levanta exceção para fora de `probe()`.
"""
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

_CTX = ssl._create_unverified_context()
_UA = {"User-Agent": "Mozilla/5.0 InvenSync"}


def base_url(ip: str) -> str:
    """Normaliza o IP/host de gerência para uma URL http:// (se já não tiver esquema)."""
    ip = (ip or "").strip()
    if not ip:
        return ""
    return ip if "://" in ip else "http://" + ip


def auth_url(ip: str, user: str, password: str) -> str:
    """URL com credenciais embutidas para Basic Auth: http://user:senha@host."""
    b = base_url(ip)
    if not b:
        return ""
    parts = urlsplit(b)
    userinfo = quote(user or "", safe="")
    if password:
        userinfo += ":" + quote(password, safe="")
    netloc = f"{userinfo}@{parts.netloc}" if userinfo else parts.netloc
    return f"{parts.scheme}://{netloc}{parts.path or ''}"


def _get(url, timeout):
    req = urllib.request.Request(url, headers=_UA, method="GET")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            body = r.read(4000).decode("latin-1", "replace")
            return r.status, dict(r.headers), body, time.monotonic() - t0
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(4000).decode("latin-1", "replace")
        except Exception:  # noqa: BLE001
            pass
        return e.code, dict(e.headers or {}), body, time.monotonic() - t0
    except Exception:  # noqa: BLE001
        return None, {}, "", None


def _auth_kind(status, headers, body):
    wa = headers.get("WWW-Authenticate") or headers.get("Www-Authenticate") or ""
    wal = wa.lower()
    realm = ""
    if 'realm="' in wal:
        try:
            realm = wa.split('realm="', 1)[1].split('"', 1)[0]
        except Exception:  # noqa: BLE001
            realm = ""
    if "basic" in wal:
        return "basic", realm
    if "digest" in wal:
        return "digest", realm
    low = body.lower()
    if status and status < 500 and ('type="password"' in low or "type=password" in low):
        return "form", ""
    return "unknown", ""


def probe(ip: str, timeout: float = 4.0) -> dict:
    """Sonda o painel admin SEM enviar credencial. Sempre devolve um dict.

    auth_kind: basic | digest | form | unknown | offline | sem-ip
    """
    b = base_url(ip)
    if not b:
        return {"online": False, "auth_kind": "sem-ip", "latency_ms": None, "realm": "", "url": ""}
    cands = [b]
    if "://" not in (ip or ""):
        cands.append("https://" + ip.strip())
    for url in cands:
        status, headers, body, dt = _get(url, timeout)
        if status is not None:
            kind, realm = _auth_kind(status, headers, body)
            return {"online": True, "auth_kind": kind, "realm": realm,
                    "latency_ms": int(dt * 1000) if dt is not None else None,
                    "url": url, "http_status": status}
    return {"online": False, "auth_kind": "offline", "latency_ms": None, "realm": "", "url": b}
