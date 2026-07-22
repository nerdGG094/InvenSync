"""Coleta periódica das impressoras via SNMP: grava histórico dos contadores
(PrinterReading) e avisa a TI por e-mail quando toner/cilindro fica baixo.

Roda numa thread de fundo (como o monitoramento de uptime). Cada varredura:
  1. consulta cada impressora de rede ativa (services.snmp_printer),
  2. grava UMA leitura por impressora (páginas + toner% + cilindro%),
  3. e-mail à TI quando um suprimento cruza o limite — UMA vez por queda (só
     reavisa depois que a troca fizer o nível voltar acima do limite + folga).
"""
import os
import threading
import time
from datetime import datetime

from ..extensions import db

_started = False
_lock = threading.Lock()

# Estado em memória do "já avisei": machine_id -> {"toner": bool, "drum": bool}.
_alerted = {}


def _limite(app):
    return int(app.config.get("PRINTER_SUPPLY_ALERT_PCT", 10) or 10)


def collect_once(app):
    """Uma varredura completa. Retorna (lidas, avisos_enviados)."""
    from ..models.machine import Machine
    from ..models.printer_reading import PrinterReading
    from . import snmp_printer, mailer, audit

    with app.app_context():
        community = app.config.get("SNMP_COMMUNITY", "public")
        timeout = float(app.config.get("SNMP_TIMEOUT", 3))
        limite = _limite(app)
        folga = 5  # só re-arma o alerta quando subir acima de (limite + folga)

        impressoras = (Machine.query
                       .filter_by(kind="impressora", is_active=True)
                       .filter(Machine.ip_address.isnot(None))
                       .all())
        lidas, avisos = 0, 0
        for m in impressoras:
            d = snmp_printer.query(m.ip_address, community=community, timeout=timeout)
            if not d.get("ok"):
                continue
            drum = next((s["pct"] for s in d.get("supplies", [])
                         if s.get("pct") is not None and "drum" in (s.get("desc") or "").lower()),
                        None)
            # Sem nada mensurável (ex.: Canon de tanque via IPP)? Não grava linha
            # vazia — o consumo dessas vem por leitura manual.
            if d.get("pages") is None and d.get("toner_pct") is None and drum is None:
                continue
            db.session.add(PrinterReading(
                machine_id=m.id, pages=d.get("pages"),
                toner_pct=d.get("toner_pct"), drum_pct=drum))
            lidas += 1

            st = _alerted.setdefault(m.id, {"toner": False, "drum": False})
            for chave, pct, rotulo in (("toner", d.get("toner_pct"), "Toner"),
                                       ("drum", drum, "Cilindro")):
                if pct is None:
                    continue
                if pct <= limite and not st[chave]:
                    st[chave] = True
                    avisos += 1
                    mailer.notify_ti(
                        f"[InvenSync] 🖨️ {rotulo} baixo: {m.model or m.name} ({m.sector or 's/ setor'})",
                        f"A impressora '{m.model or m.name}' ({m.ip_address}) está com "
                        f"{rotulo.lower()} em {pct}%.\nSetor: {m.sector or '—'}.\n"
                        f"Providencie a troca.")
                    audit.record("update", "machine", m.id,
                                 f"{rotulo} baixo ({pct}%) em '{m.model or m.name}'")
                elif pct >= limite + folga and st[chave]:
                    st[chave] = False   # trocou/recuperou: re-arma o alerta
        db.session.commit()
        return lidas, avisos


def start_scheduler(app):
    global _started
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    if not app.config.get("PRINTER_MONITOR_ENABLED", True):
        return
    with _lock:
        if _started:
            return
        _started = True

    intervalo = max(10, int(app.config.get("PRINTER_MONITOR_MINUTES", 60) or 60)) * 60

    def loop():
        time.sleep(40)   # deixa o servidor subir antes da 1ª coleta
        while True:
            try:
                collect_once(app)
            except Exception:  # noqa: BLE001
                try:
                    with app.app_context():
                        db.session.rollback()
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(intervalo)

    threading.Thread(target=loop, daemon=True, name="printer-monitor").start()
