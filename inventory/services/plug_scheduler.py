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

    def loop():
        time.sleep(20)  # deixa o servidor subir
        while True:
            try:
                run_due(app)
            except Exception:  # noqa: BLE001
                try:
                    with app.app_context():
                        db.session.rollback()
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(30)   # 2x por minuto: nenhum minuto é pulado

    threading.Thread(target=loop, daemon=True, name="plug-scheduler").start()
