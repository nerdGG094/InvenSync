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

from ..extensions import db

_started = False
_lock = threading.Lock()

# Estado em memória do "já avisei": machine_id -> {"toner": bool, "drum": bool}.
_alerted = {}
# Último nível lido por suprimento: machine_id -> {"toner": pct|None, "drum": pct|None}.
# Serve para detectar a TROCA (subiu de baixo p/ cheio entre duas leituras).
_last_pct = {}


def _limite(app):
    return int(app.config.get("PRINTER_SUPPLY_ALERT_PCT", 10) or 10)


def _registrar_troca(m, chave, rotulo, prev_pct, pct):
    """Troca detectada (nível subiu de baixo p/ cheio): dá baixa de 1 unidade do
    material ligado à impressora e avisa a TI se o estoque estava zerado.
    Retorna 1 se movimentou, 0 caso contrário."""
    from ..models.product import Product
    from ..models.movement import StockMovement
    from ..repositories import product_repo
    from . import mailer, audit

    prod_id = m.toner_product_id if chave == "toner" else m.drum_product_id
    if not prod_id:
        return 0  # impressora sem material vinculado — nada a movimentar
    prod = db.session.get(Product, prod_id)
    if not prod:
        return 0

    saldo = product_repo.current_stock(prod)  # antes da baixa
    db.session.add(StockMovement(
        product_id=prod_id, movement_type="OUT", quantity=1,
        note=(f"Troca automática ({rotulo.lower()}) detectada via SNMP na impressora "
              f"'{m.model or m.name}' ({m.sector or 's/ setor'}): {prev_pct}% → {pct}%.")))
    db.session.commit()
    audit.record("update", "product", prod_id,
                 f"Baixa automática de {rotulo.lower()} (troca na impressora "
                 f"'{m.model or m.name}')")
    if saldo <= 0:
        mailer.notify_ti(
            f"[InvenSync] 📦 Estoque zerado: {prod.name}",
            f"A troca de {rotulo.lower()} na impressora '{m.model or m.name}' "
            f"({m.sector or '—'}) deu baixa de 1 un de '{prod.name}' (SKU {prod.sku}), "
            f"mas o saldo estava em {saldo}. Reponha o material.")
    return 1


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
        alto = int(app.config.get("PRINTER_REPLACE_PCT", 80) or 80)   # nível de "cheio" p/ troca
        salto = int(app.config.get("PRINTER_REPLACE_JUMP", 40) or 40)  # subida mínima p/ contar troca

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
            # vazia — dessas só temos estado/alertas ao vivo, sem contador.
            if d.get("pages") is None and d.get("toner_pct") is None and drum is None:
                continue
            db.session.add(PrinterReading(
                machine_id=m.id, pages=d.get("pages"),
                toner_pct=d.get("toner_pct"), drum_pct=drum))
            lidas += 1

            st = _alerted.setdefault(m.id, {"toner": False, "drum": False})
            prev = _last_pct.setdefault(m.id, {"toner": None, "drum": None})
            for chave, pct, rotulo in (("toner", d.get("toner_pct"), "Toner"),
                                       ("drum", drum, "Cilindro")):
                if pct is None:
                    continue
                # Troca: o nível deu um salto grande p/ cima (>= salto) e chegou
                # perto do cheio (>= alto) entre duas leituras -> baixa de 1 unidade
                # do material vinculado. Pega trocas feitas em 20%, 15% etc., não só
                # abaixo do limite de alerta.
                if (prev[chave] is not None and pct >= alto
                        and (pct - prev[chave]) >= salto):
                    _registrar_troca(m, chave, rotulo, prev[chave], pct)
                prev[chave] = pct
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
