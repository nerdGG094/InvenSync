"""Alertas de atividade suspeita: baseline na 1ª rodada, dispara ao cruzar limite."""
import pytest

from inventory.extensions import db
from inventory.models.audit import AuditLog
from inventory.services import alerts

MARK = "PYTEST-SEC"


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        AuditLog.query.filter(AuditLog.summary.like(f"{MARK}%")).delete()
        db.session.commit()
    # zera o estado do detector para não vazar entre testes
    import os
    p = alerts._sec_state_file(app)
    if os.path.exists(p):
        os.remove(p)


def test_suspicious_activity_triggers_on_reveal_burst(app):
    with app.app_context():
        app.config["SEC_ALERT_REVEAL"] = 3
        # 1ª rodada: só marca o ponto de partida (sem alerta retroativo).
        assert alerts.check_suspicious_activity(app) == []
        # 4 revelações do Cofre acima do limite (3).
        for i in range(4):
            db.session.add(AuditLog(action="reveal", entity="credential",
                                    summary=f"{MARK} reveal {i}"))
        db.session.commit()
        hits = alerts.check_suspicious_activity(app)
        assert any("revela" in h.lower() for h in hits)
        # rodada seguinte, sem novos registros → nada.
        assert alerts.check_suspicious_activity(app) == []
