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

# --- Proteção do DVR -------------------------------------------------------
# Estes aparelhos têm tabela de conexões pequena. Uma grade de 32 canais abre
# ~10 conexões HTTP novas por segundo e chega a DERRUBAR o serviço web do DVR:
# ele para de aceitar SYN, o painel some, os eventos param — só o RTSP sobrevive.
# Duas travas: no máximo N buscas simultâneas por aparelho, e uma pausa após
# falhas seguidas (em vez de insistir e piorar).
_MAX_SIMULTANEAS = 4
_FALHAS_ATE_PAUSAR = 5
_PAUSA = 30.0                 # segundos sem tentar, após a sequência de falhas

_vagas = {}                   # did -> Semaphore
_falhas = {}                  # did -> [falhas seguidas, momento da pausa]


def _semaforo(did):
    with _lock:
        s = _vagas.get(did)
        if s is None:
            s = _vagas[did] = threading.Semaphore(_MAX_SIMULTANEAS)
        return s


def _em_pausa(did) -> bool:
    with _lock:
        st = _falhas.get(did)
        return bool(st and st[1] and time.time() < st[1])


def _registrar(did, ok):
    with _lock:
        st = _falhas.setdefault(did, [0, 0.0])
        if ok:
            st[0], st[1] = 0, 0.0
        else:
            st[0] += 1
            if st[0] >= _FALHAS_ATE_PAUSAR:
                st[1] = time.time() + _PAUSA


def saude(did) -> dict:
    """Como está o aparelho do ponto de vista do proxy (para diagnóstico)."""
    with _lock:
        st = _falhas.get(did) or [0, 0.0]
        restam = max(0.0, st[1] - time.time()) if st[1] else 0.0
    return {"falhas_seguidas": st[0], "pausado_por": round(restam, 1)}


def porta_aberta(host, porta, timeout=2.0) -> bool:
    """Teste TCP simples. Serve para saber se o APARELHO está vivo quando o
    painel HTTP não responde — o serviço web do DVR trava sozinho de vez em
    quando, enquanto RTSP e gravação seguem normais."""
    import socket
    from urllib.parse import urlsplit
    host = (host or "").strip()
    if not host:
        return False
    if "://" in host:
        host = urlsplit(host).hostname or ""
    try:
        s = socket.create_connection((host, int(porta)), timeout=timeout)
        s.close()
        return True
    except Exception:  # noqa: BLE001
        return False


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
    """JPEG do canal `ch` (bytes) ou None. Usa cache de `ttl` segundos.

    Devolve None de imediato se o aparelho está em pausa (sequência de falhas)
    ou se já há buscas demais em curso — melhor a miniatura piscar "sem sinal"
    do que empilhar conexões e derrubar o serviço web do DVR (já aconteceu)."""
    key = (d.id, int(ch))
    now = time.time()
    with _lock:
        c = _cache.get(key)
        if c and now - c[0] < ttl:
            return c[1]

    if _em_pausa(d.id):
        return None

    vaga = _semaforo(d.id)
    if not vaga.acquire(blocking=False):
        # Sem vaga: entrega a última foto conhecida, mesmo vencida, em vez de
        # esperar (segurar uma thread do servidor à toa).
        with _lock:
            c = _cache.get(key)
        return c[1] if c else None

    try:
        try:
            data = _fetch(d, pw, ch, timeout)
        except Exception:  # noqa: BLE001 — nonce expirou/erro: recria e tenta 1x
            _openers.pop(d.id, None)
            try:
                data = _fetch(d, pw, ch, timeout)
            except Exception:  # noqa: BLE001
                _registrar(d.id, False)
                return None
    finally:
        vaga.release()

    _registrar(d.id, True)
    with _lock:
        _cache[key] = (now, data)
    return data
