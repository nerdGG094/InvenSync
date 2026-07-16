"""Agendador das tomadas: dispara a regra devida e não repete no mesmo minuto."""
from datetime import datetime

import pytest

from inventory.extensions import db
from inventory.models.smart_plug import SmartPlug
from inventory.models.smart_plug_schedule import SmartPlugSchedule
from inventory.services import plug_scheduler

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        SmartPlug.query.filter(SmartPlug.name.like(f"{MARK}%")).delete()
        db.session.commit()


def test_scheduler_marks_slot_and_matches_day(app, monkeypatch):
    with app.app_context():
        plug = SmartPlug(name=f"{MARK} Sched", device_id="bfX", ip_address=None, local_key=None)
        db.session.add(plug)
        db.session.commit()
        now = datetime.now()
        s = SmartPlugSchedule(plug_id=plug.id, action="off", hour=now.hour,
                              minute=now.minute, days="")   # todo dia
        db.session.add(s)
        db.session.commit()
        sid = s.id

        # tuya.set_state é no-op controlado (tomada sem IP/key retornaria erro real);
        # forçamos ok=True para validar o fluxo do agendador.
        monkeypatch.setattr("inventory.services.tuya.set_state",
                            lambda p, on: {"ok": True, "on": on})

        fired = plug_scheduler.run_due(app)
        assert fired == 1
        db.session.refresh(s)
        slot = datetime.now().strftime("%Y%m%d%H%M")
        assert s.last_fired_slot == slot

        # segunda chamada no mesmo minuto não repete
        assert plug_scheduler.run_due(app) == 0


def test_matches_day_and_labels(app):
    with app.app_context():
        s = SmartPlugSchedule(action="on", hour=7, minute=0, days="15")  # Seg e Sex
        assert s.matches_day(1) and s.matches_day(5)
        assert not s.matches_day(2)
        assert s.hhmm == "07:00"
        s2 = SmartPlugSchedule(action="on", hour=8, minute=30, days="")
        assert s2.matches_day(3) and s2.days_label() == "Todos os dias"
