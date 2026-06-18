"""
Monitoramento de uptime (ping/HTTP) de hosts da rede.

- Verifica hosts cadastrados (servidores, impressoras, roteadores, sites).
- Roda em background (thread daemon) a cada MONITORING_INTERVAL segundos.
- Quando um host CAI (up->down) ou VOLTA (down->up), avisa a TI por WhatsApp
  (CallMeBot) — reaproveita o serviço já existente.

Tolerante a falhas: qualquer erro de verificação nunca derruba o app/servidor.
"""
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from ..extensions import db
from ..models.monitor import MonitoredHost
from . import whatsapp

# Quantas falhas seguidas antes de marcar como "down" (evita alarme por 1 perda de pacote)
FAIL_THRESHOLD = 2

_started = False
_lock = threading.Lock()

KIND_LABELS = {
    "servidor": "Servidor", "impressora": "Impressora", "roteador": "Roteador",
    "switch": "Switch", "site": "Site", "outro": "Outro",
}


# ---------------------------------------------------------------------------
# Verificadores de baixo nível
# ---------------------------------------------------------------------------
def ping_host(host: str, timeout_ms: int = 2000):
    """Faz 1 ping. Retorna (up: bool, latency_ms: int|None)."""
    host = (host or "").strip()
    if not host:
        return False, None
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
        creationflags = 0x08000000  # CREATE_NO_WINDOW
    else:
        secs = max(1, round(timeout_ms / 1000))
        cmd = ["ping", "-c", "1", "-W", str(secs), host]
        creationflags = 0
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=max(3, timeout_ms / 1000 + 2),
            creationflags=creationflags,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        # "up" de verdade: precisa ter resposta com TTL (evita "host inacessível" que retorna 0)
        up = ("ttl=" in out.lower())
        latency = None
        m = re.search(r"(?:tempo|time)[=<]\s*(\d+)\s*ms", out, re.IGNORECASE)
        if m:
            latency = int(m.group(1))
        return up, latency
    except Exception:  # noqa: BLE001
        return False, None


def http_check(url: str, timeout: int = 6):
    """GET simples. Retorna (up, latency_ms). up = resposta HTTP < 400."""
    url = (url or "").strip()
    if not url:
        return False, None
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    try:
        t0 = time.monotonic()
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "InvenSync-Monitor"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            latency = int((time.monotonic() - t0) * 1000)
            return (200 <= r.status < 400), latency
    except urllib.error.HTTPError as e:  # noqa: F821  (urllib.error vem via urllib.request)
        # Respondeu, mas com erro HTTP: consideramos "no ar" se < 500
        latency = int((time.monotonic() - t0) * 1000)
        return (e.code < 500), latency
    except Exception:  # noqa: BLE001
        return False, None


def _check_one(h: MonitoredHost):
    if h.check_type == "http":
        return http_check(h.host)
    return ping_host(h.host)


# ---------------------------------------------------------------------------
# Verificação em lote (atualiza o banco + dispara alertas)
# ---------------------------------------------------------------------------
def check_all(app):
    """Verifica todos os hosts habilitados. Roda dentro de um app_context."""
    transitions = []  # (host, novo_status)
    with app.app_context():
        try:
            hosts = MonitoredHost.query.filter_by(enabled=True).all()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return []
        now = datetime.now()
        for h in hosts:
            up, latency = _check_one(h)
            prev = h.last_status
            h.last_checked = now
            h.last_latency_ms = latency if up else None

            if up:
                h.fail_count = 0
                novo = "up"
            else:
                h.fail_count = (h.fail_count or 0) + 1
                # Só vira "down" após N falhas seguidas (ou se já estava down)
                novo = "down" if (h.fail_count >= FAIL_THRESHOLD or prev == "down") else prev

            if novo != prev and prev != "unknown":
                h.last_change = now
                transitions.append((h, novo))
            elif novo != prev:  # primeira definição (unknown -> up/down): registra sem alertar
                h.last_change = now
            h.last_status = novo

        try:
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return []

        # Alertas (best-effort) só para transições reais
        for h, novo in transitions:
            try:
                if novo == "down":
                    whatsapp.notify_ti(
                        f"🔴 *Host fora do ar*: {h.label} ({h.host})\n"
                        f"Tipo: {KIND_LABELS.get(h.kind, h.kind)}\n"
                        f"Detectado em {now.strftime('%d/%m %H:%M')}"
                    )
                elif novo == "up":
                    whatsapp.notify_ti(
                        f"🟢 *Host restabelecido*: {h.label} ({h.host})\n"
                        f"Voltou em {now.strftime('%d/%m %H:%M')}"
                    )
            except Exception:  # noqa: BLE001
                pass
    return [(h.id, novo) for h, novo in transitions]


# ---------------------------------------------------------------------------
# Agendador em background
# ---------------------------------------------------------------------------
def start_scheduler(app):
    """Inicia uma thread daemon que verifica os hosts periodicamente.

    Idempotente por processo. Respeita o reloader do Flask (não duplica)."""
    global _started
    import os
    # Sob o reloader do Flask (debug), só roda no processo filho real.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    with _lock:
        if _started:
            return
        _started = True

    interval = int(app.config.get("MONITORING_INTERVAL", 120) or 120)

    def loop():
        # Pequeno atraso inicial para o servidor terminar de subir.
        time.sleep(10)
        while True:
            try:
                check_all(app)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="uptime-monitor").start()
    try:
        app.logger.info("Monitoramento de uptime iniciado (intervalo=%ss).", interval)
    except Exception:  # noqa: BLE001
        pass
