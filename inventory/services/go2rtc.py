"""go2rtc — vídeo ao vivo (WebRTC) das câmeras dos DVRs.

O snapshot (`services/dvr_cam.py`) tem teto de ~1 fps: o `snapshot.cgi` destes
DVRs leva ~0,9 s por foto. Para vídeo fluido (sub-segundo) usamos o **go2rtc**:
um binário externo (MIT, ~20-40 MB) que lê o RTSP do DVR e entrega ao navegador
por **WebRTC em passthrough** — não transcodifica, então o gasto de CPU é baixo
e só há tráfego enquanto alguém está assistindo.

Este módulo NÃO embute o go2rtc. Ele só:
  - monta o nome e a URL RTSP de cada canal a partir da tabela `dvr`;
  - **gera o `go2rtc.yaml`** com um stream por canal (senha decifrada do cofre);
  - devolve a URL do player (iframe) por DVR/canal;
  - sonda se o serviço está no ar (`probe`).

Tudo best-effort: com `GO2RTC_URL` vazio o módulo fica desligado e a página de
câmeras continua funcionando só com snapshot.

ATENÇÃO: o `go2rtc.yaml` gerado contém usuário e senha dos DVRs em texto puro
(é o formato que o go2rtc entende). Ele fica fora do Git (.gitignore) — mantenha
a pasta com acesso restrito, como o `.env`.
"""
import json
import os
import re
import time
import urllib.request
from urllib.parse import quote, urlsplit

from flask import current_app

from . import crypto

_UA = {"User-Agent": "Mozilla/5.0 InvenSync"}
# Linha-chave de um stream no arquivo gerado (serve p/ contar as câmeras).
_STREAM_KEY = re.compile(r"^  dvr\d+_ch\d+:")

# Intelbras/Dahua — caminho e codecs CONFERIDOS nos DVRs da empresa:
#   /cam/realmonitor  (singular; "cams" devolve 404)
#   subtype=0 -> principal: 720p, mas **H.265** (o WebRTC não transporta)
#   subtype=1 -> sub-stream: H.264, porém **CIF 352x240 @ 7 fps** — e o DVR não
#                deixa subir (ResolutionTypes=CIF). É a imagem "SD" ruim.
# Por isso o padrão é o principal (HD) + uma 2ª fonte `ffmpeg:` que converte
# para H.264 sob demanda, só quando o navegador não aceita H.265.
DEFAULT_TEMPLATE = ("rtsp://{user}:{password}@{host}:{port}"
                    "/cam/realmonitor?channel={channel}&subtype={subtype}")

MASK = "********"


# --------------------------------------------------------------------------- #
# Configuração / URLs
# --------------------------------------------------------------------------- #
def base_url() -> str:
    """URL do go2rtc (ex.: http://192.168.0.54:1984) ou "" se desligado."""
    u = (current_app.config.get("GO2RTC_URL") or "").strip().rstrip("/")
    if u and "://" not in u:
        u = "http://" + u
    return u


def enabled() -> bool:
    return bool(base_url())


def config_path() -> str:
    return current_app.config.get("GO2RTC_CONFIG") or ""


def stream_name(d, ch) -> str:
    """Nome do stream no go2rtc — estável e único por (DVR, canal)."""
    return f"dvr{d.id}_ch{int(ch)}"


def stream_title(d, ch) -> str:
    return f"{d.location or d.label or d.model} · CH {int(ch)}"


def _host(d) -> str:
    """Só o host/IP do DVR (o campo pode vir com esquema: http://x)."""
    ip = (d.ip_address or "").strip()
    if not ip:
        return ""
    return (urlsplit(ip).hostname or "") if "://" in ip else ip


def rtsp_url(d, ch, password=None, mask=False) -> str:
    """URL RTSP do canal `ch`. `mask=True` troca a senha por asteriscos (exibição)."""
    host = _host(d)
    if not host:
        return ""
    if password is None and not mask:
        password = crypto.decrypt(d.admin_password) or ""
    cfg = current_app.config
    tpl = cfg.get("GO2RTC_RTSP_TEMPLATE") or DEFAULT_TEMPLATE
    return tpl.format(
        user=quote(d.admin_user or "admin", safe=""),
        password=MASK if mask else quote(password or "", safe=""),
        host=host,
        port=int(cfg.get("GO2RTC_RTSP_PORT", 554) or 554),
        channel=int(ch),
        subtype=int(cfg.get("GO2RTC_SUBTYPE", 0) or 0),
    )


def player_url(d, ch) -> str:
    """URL da página do player do go2rtc (usada num <iframe>)."""
    b = base_url()
    if not b:
        return ""
    mode = current_app.config.get("GO2RTC_PLAYER_MODE") or "webrtc,mse"
    return f"{b}/stream.html?src={quote(stream_name(d, ch), safe='')}&mode={quote(mode, safe=',')}"


def player_urls(d, canais, names=None) -> dict:
    """{canal: url} dos canais que o go2rtc conhece.

    `names` é a lista vinda de `probe()`; sem ela assume que todos existem
    (a página cai no snapshot sozinha se o player não carregar)."""
    if not enabled():
        return {}
    conhecidos = set(names) if names is not None else None
    return {int(ch): player_url(d, ch) for ch in canais
            if conhecidos is None or stream_name(d, ch) in conhecidos}


# --------------------------------------------------------------------------- #
# Geração do go2rtc.yaml
# --------------------------------------------------------------------------- #
def _yaml_str(v: str) -> str:
    """Escalar YAML entre aspas duplas (a URL tem :, ?, & e pode ter aspas)."""
    return '"' + (v or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def eligible(dvrs):
    """DVRs que viram streams: ativos, com IP e com nº de canais."""
    return [d for d in dvrs
            if d.status != "inativo" and _host(d) and (d.channels or 0) > 0]


def ffmpeg_bin() -> str:
    """Caminho do ffmpeg.exe (para transcodificar H.265 -> H.264 sob demanda).

    Sem configuração explícita, procura ao lado do go2rtc.yaml; se não achar,
    devolve "" e o go2rtc tenta o PATH.
    """
    p = (current_app.config.get("GO2RTC_FFMPEG") or "").strip()
    if p:
        return p
    pasta = os.path.dirname(os.path.abspath(config_path() or ""))
    cand = os.path.join(pasta, "ffmpeg.exe") if pasta else ""
    return cand if cand and os.path.isfile(cand) else ""


def transcode_enabled() -> bool:
    return bool(current_app.config.get("GO2RTC_TRANSCODE", True))


def build_config(dvrs, mask=False):
    """Monta o texto do go2rtc.yaml. Devolve (texto, nº de streams).

    Cada canal vira um stream com até duas fontes:
      1. o RTSP do DVR (720p; nestes aparelhos, H.265);
      2. `ffmpeg:<stream>#video=h264` — a MESMA fonte convertida para H.264.
    O go2rtc escolhe pela negociação de codec: navegador com H.265 assiste em
    passthrough (CPU zero); sem H.265, entra a conversão — só enquanto alguém
    estiver assistindo àquele canal.

    `mask=True` gera a mesma coisa com a senha escondida — é o que a tela mostra.
    Pode levantar `crypto.DecryptError` se a VAULT_KEY não bate com o cadastro.
    """
    alvos = eligible(dvrs)
    ff = ffmpeg_bin()
    transcode = transcode_enabled()
    linhas = [
        "# === go2rtc — arquivo GERADO pelo InvenSync (módulo CFTV) ===",
        "# Não edite à mão: a tela /cftv/go2rtc regrava este arquivo a partir",
        "# dos DVRs cadastrados. Contém usuário e senha dos DVRs em texto puro —",
        "# mantenha o acesso restrito (mesmo cuidado do .env).",
        "",
        "api:",
        '  listen: ":1984"      # painel/API do go2rtc (o navegador acessa aqui)',
        "",
        "webrtc:",
        '  listen: ":8555"      # WebRTC (TCP+UDP); libere no firewall da rede interna',
        "",
        "rtsp:",
        '  listen: ":8554"',
        "",
        "log:",
        "  level: info",
        "",
    ]
    if transcode and ff:
        linhas += ["ffmpeg:", f"  bin: {_yaml_str(ff)}", ""]
    linhas.append("streams:")
    n = 0
    if not alvos:
        linhas.append("  # (nenhum DVR ativo com IP e canais cadastrados)")
    for d in alvos:
        linhas.append(f"  # {d.location or d.label or d.model} — {_host(d)} · {d.channels} canais")
        pw = None if mask else (crypto.decrypt(d.admin_password) or "")
        for ch in range(1, int(d.channels) + 1):
            nome = stream_name(d, ch)
            url = rtsp_url(d, ch, password=pw, mask=mask)
            if transcode:
                linhas.append(f"  {nome}:")
                linhas.append(f"    - {_yaml_str(url)}")
                linhas.append(f"    - \"ffmpeg:{nome}#video=h264\"")
            else:
                linhas.append(f"  {nome}: {_yaml_str(url)}")
            n += 1
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n", n


def write_config(dvrs, path=None):
    """Grava o go2rtc.yaml. Devolve (caminho, nº de streams)."""
    path = path or config_path()
    if not path:
        raise ValueError("GO2RTC_CONFIG não configurado")
    texto, n = build_config(dvrs)
    pasta = os.path.dirname(os.path.abspath(path))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)
    return path, n


def config_status() -> dict:
    """Estado do arquivo gerado (existe? quando? quantos streams?)."""
    p = config_path()
    if not p or not os.path.isfile(p):
        return {"path": p, "exists": False, "mtime": None, "streams": 0}
    try:
        with open(p, encoding="utf-8") as fh:
            linhas = fh.read().splitlines()
        n = sum(1 for ln in linhas if _STREAM_KEY.match(ln))
        return {"path": p, "exists": True, "streams": n,
                "mtime": time.strftime("%d/%m/%Y %H:%M",
                                       time.localtime(os.path.getmtime(p)))}
    except OSError:
        return {"path": p, "exists": True, "mtime": None, "streams": 0}


# --------------------------------------------------------------------------- #
# Sondagem do serviço
# --------------------------------------------------------------------------- #
def _get_json(url, timeout):
    req = urllib.request.Request(url, headers=_UA, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(1_000_000).decode("utf-8", "replace"))


_probe_cache = {}   # url -> (ts, dict)


def probe(timeout=None, ttl=0.0) -> dict:
    """Sonda o go2rtc. Sempre devolve um dict; nunca levanta.

    `ttl` reaproveita a última resposta por N segundos — usado na página de
    câmeras para não pagar o timeout a cada abertura quando o serviço está fora.
    """
    b = base_url()
    if not b:
        return {"enabled": False, "online": False, "url": "", "streams": 0,
                "version": "", "names": []}
    if ttl:
        got = _probe_cache.get(b)
        if got and time.time() - got[0] < ttl:
            return got[1]
    timeout = float(timeout or current_app.config.get("GO2RTC_TIMEOUT", 3) or 3)
    out = {"enabled": True, "online": False, "url": b, "streams": 0,
           "version": "", "names": []}
    try:
        data = _get_json(f"{b}/api/streams", timeout)
        out["online"] = True
        if isinstance(data, dict):
            out["names"] = sorted(data.keys())
            out["streams"] = len(data)
    except Exception:  # noqa: BLE001 — serviço fora do ar / porta fechada
        _probe_cache[b] = (time.time(), out)
        return out
    try:
        info = _get_json(f"{b}/api", timeout)
        if isinstance(info, dict):
            out["version"] = str(info.get("version") or "")
    except Exception:  # noqa: BLE001 — versão é só informativo
        pass
    _probe_cache[b] = (time.time(), out)
    return out
