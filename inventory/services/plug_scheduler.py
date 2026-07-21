"""Agendador das tomadas inteligentes: liga/desliga no horário programado.

Thread daemon que acorda a cada ~30s e dispara as regras cujo horário/dia batem
com o momento atual, comandando a tomada localmente (services.tuya). Usa
`last_fired_slot` (minuto YYYYMMDDHHMM) para nunca repetir no mesmo minuto.
Requer o servidor no ar — se estiver fora do ar na hora, a regra não roda.
"""
import os
import threading
import time
from datetime import datetime

from ..extensions import db

_started = False
_lock = threading.Lock()


def run_due(app):
    """Dispara as regras devidas neste minuto. Retorna quantas disparou."""
    with app.app_context():
        from ..models.smart_plug_schedule import SmartPlugSchedule
        from . import tuya, audit
        now = datetime.now()
        slot = now.strftime("%Y%m%d%H%M")
        iso = now.isoweekday()
        due = (SmartPlugSchedule.query
               .filter_by(is_active=True, hour=now.hour, minute=now.minute).all())
        fired = 0
        for s in due:
            if s.last_fired_slot == slot or not s.matches_day(iso):
                continue
            s.last_fired_slot = slot
            plug = s.plug
            if not plug or not plug.is_active:
                db.session.commit()
                continue
            res = tuya.set_state(plug, s.action == "on")
            db.session.commit()
            if res.get("ok"):
                fired += 1
                audit.record("update", "smart_plug", plug.id,
                             f"Agendamento {'ligou' if s.action == 'on' else 'desligou'} '{plug.name}'")
        return fired


def check_offline(app):
    """Consulta cada tomada ativa e avisa a TI por e-mail quando uma fica
    inalcançável por mais de PLUG_OFFLINE_ALERT_MINUTES. Avisa UMA vez por queda
    (e manda o 'voltou' quando ela responde de novo). Retorna (caidas, voltaram)."""
    with app.app_context():
        from ..models.smart_plug import SmartPlug
        from . import tuya, mailer, audit
        # Atenção: 0 é valor válido (avisar na hora) — não usar `or` aqui.
        _lim = app.config.get("PLUG_OFFLINE_ALERT_MINUTES", 30)
        limite = 30 if _lim is None else int(_lim)
        agora = datetime.now()
        caidas, voltaram = [], []
        for plug in SmartPlug.query.filter_by(is_active=True).all():
            ok = bool(tuya.get_status(plug).get("ok"))
            if ok:
                if plug.offline_alerted:      # estava fora e voltou
                    voltaram.append(plug)
                plug.last_seen = agora
                plug.offline_since = None
                plug.offline_alerted = False
            else:
                if plug.offline_since is None:
                    plug.offline_since = agora
                fora_min = (agora - plug.offline_since).total_seconds() / 60.0
                if fora_min >= limite and not plug.offline_alerted:
                    plug.offline_alerted = True
                    caidas.append(plug)
        db.session.commit()

        # Retorna dados simples (não objetos ORM): ao sair do app_context a
        # sessão é encerrada e as instâncias ficariam "detached".
        info_caidas, info_voltaram = [], []
        for plug in caidas:
            desde = plug.offline_since.strftime("%d/%m %H:%M") if plug.offline_since else "?"
            mailer.notify_ti(
                f"[InvenSync] ⚠️ Tomada offline: {plug.name}",
                f"A tomada '{plug.name}' ({plug.ip_address or 'sem IP'}) não responde "
                f"desde {desde}.\n\nOs agendamentos dela NÃO vão disparar enquanto estiver fora.\n"
                f"Confira se está energizada e se o IP mudou (DHCP).")
            audit.record("update", "smart_plug", plug.id, f"Tomada '{plug.name}' offline")
            info_caidas.append({"id": plug.id, "name": plug.name})
        for plug in voltaram:
            mailer.notify_ti(
                f"[InvenSync] ✅ Tomada voltou: {plug.name}",
                f"A tomada '{plug.name}' ({plug.ip_address or 'sem IP'}) voltou a responder.")
            audit.record("update", "smart_plug", plug.id, f"Tomada '{plug.name}' voltou")
            info_voltaram.append({"id": plug.id, "name": plug.name})
        return info_caidas, info_voltaram


def start_scheduler(app):
    global _started
    # Sob o reloader do Flask (debug), só roda no processo filho real.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    if not app.config.get("PLUG_SCHEDULER_ENABLED", True):
        return
    with _lock:
        if _started:
            return
        _started = True

    # De quanto em quanto tempo consultar a disponibilidade das tomadas.
    check_min = max(1, int(app.config.get("PLUG_OFFLINE_CHECK_MINUTES", 10) or 10))

    def loop():
        time.sleep(20)  # deixa o servidor subir
        proxima_checagem = 0.0
        while True:
            try:
                run_due(app)
                # Checagem de offline num ritmo próprio (consultar a rede é caro).
                if time.monotonic() >= proxima_checagem:
                    proxima_checagem = time.monotonic() + check_min * 60
                    check_offline(app)
            except Exception:  # noqa: BLE001
                try:
                    with app.app_context():
                        db.session.rollback()
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(30)   # 2x por minuto: nenhum minuto é pulado

    threading.Thread(target=loop, daemon=True, name="plug-scheduler").start()
