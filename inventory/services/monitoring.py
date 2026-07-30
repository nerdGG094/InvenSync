"""
Monitoramento de uptime (ping/HTTP) de hosts da rede.

- Verifica hosts cadastrados (servidores, impressoras, roteadores, sites).
- Roda em background (thread daemon) a cada MONITORING_INTERVAL segundos.
- Quando um host CAI (up->down) ou VOLTA (down->up), avisa a TI por e-mail.
- Impressoras, DVRs e routers ativos (com IP) entram automaticamente (auto_source),
  sem precisar cadastrar host manual — via sync_auto_hosts().

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
from . import mailer

# Quantas falhas seguidas antes de marcar como "down" (evita alarme por 1 perda de pacote)
FAIL_THRESHOLD = 2

_started = False
_lock = threading.Lock()

KIND_LABELS = {
    "servidor": "Servidor", "impressora": "Impressora", "roteador": "Roteador",
    "dvr": "DVR/CFTV", "switch": "Switch", "site": "Site", "outro": "Outro",
}


def _sync_auto_hosts():
    """Sincroniza hosts automáticos a partir de impressoras/DVRs/routers ativos
    (com IP). Executa DENTRO de um app_context. Best-effort."""
    from ..models.machine import Machine
    from ..models.dvr import Dvr
    from ..models.router import Router

    def _ipok(ip):
        ip = (ip or "").strip()
        return ip and ip.upper() != "DHCP"

    desired = {}  # auto_source -> (label, host, kind)
    try:
        for m in Machine.query.filter_by(kind="impressora", is_active=True).all():
            if _ipok(m.ip_address):
                desired[f"impressora:{m.id}"] = (m.model or m.name or "Impressora",
                                                 m.ip_address.strip(), "impressora")
        for d in Dvr.query.filter(Dvr.status != "inativo").all():
            if _ipok(d.ip_address):
                desired[f"dvr:{d.id}"] = (d.label or d.model or "DVR",
                                          d.ip_address.strip(), "dvr")
        for r in Router.query.filter(Router.status != "inativo").all():
            if _ipok(r.ip_address):
                desired[f"router:{r.id}"] = (r.label or r.model or "Roteador",
                                             r.ip_address.strip(), "roteador")
        existing = {h.auto_source: h for h in
                    MonitoredHost.query.filter(MonitoredHost.auto_source.isnot(None)).all()}
        for src, (label, host, kind) in desired.items():
            h = existing.get(src)
            if h is None:
                db.session.add(MonitoredHost(auto_source=src, label=label, host=host,
                                             kind=kind, check_type="icmp", enabled=True))
            else:
                h.label, h.host, h.kind = label, host, kind
        for src, h in existing.items():
            if src not in desired:      # equipamento removido/inativado -> remove o monitor
                db.session.delete(h)
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


def sync_auto_hosts(app):
    with app.app_context():
        _sync_auto_hosts()


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
        _sync_auto_hosts()   # mantém impressoras/DVRs/routers em dia antes de checar
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
                    mailer.notify_ti(
                        f"[InvenSync] Host fora do ar: {h.label}",
                        f"Host fora do ar: {h.label} ({h.host})\n"
                        f"Tipo: {KIND_LABELS.get(h.kind, h.kind)}\n"
                        f"Detectado em {now.strftime('%d/%m %H:%M')}"
                    )
                elif novo == "up":
                    mailer.notify_ti(
                        f"[InvenSync] Host restabelecido: {h.label}",
                        f"Host restabelecido: {h.label} ({h.host})\n"
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
            except Exception as e:  # noqa: BLE001
                try:
                    with app.app_context():
                        from . import errorlog
                        errorlog.record("monitoring", exc=e)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="uptime-monitor").start()
    try:
        app.logger.info("Monitoramento de uptime iniciado (intervalo=%ss).", interval)
    except Exception:  # noqa: BLE001
        pass
