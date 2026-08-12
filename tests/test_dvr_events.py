"""Saude e retencao da escuta de eventos dos DVRs.

A detecao ficou 6 dias fora do ar sem ninguem notar, e a tabela de
historico crescia sem limite (~6.850 linhas/dia em producao).
"""
# ---------------------------------------------------------------------------
# Regressoes da queda silenciosa: a escuta ficou 6 dias pendurada num read()
# sem timeout, e a tabela de historico crescia sem limite.
# ---------------------------------------------------------------------------
def test_escuta_tem_timeout_e_heartbeat():
    """Sem timeout, read() bloqueia para sempre quando a conexao morre calada;
    sem heartbeat, um DVR so quieto estouraria esse timeout a toa."""
    import inspect
    from inventory.services import dvr_events
    src = inspect.getsource(dvr_events._escutar)
    assert "timeout=None" not in src, "read() voltaria a bloquear indefinidamente"
    assert "_LEITURA_TIMEOUT" in src and "heartbeat" in src
    assert dvr_events._LEITURA_TIMEOUT > dvr_events._HEARTBEAT * 2, \
        "timeout precisa de folga para mais de um heartbeat"


def test_saude_reporta_escuta_caida():
    from inventory.services import dvr_events
    dvr_events._marcar_vivo(4242)
    assert dvr_events.saude()[4242]["ok"] is True
    dvr_events._marcar_morto(4242)
    assert dvr_events.saude()[4242]["ok"] is False
    dvr_events._saude.pop(4242, None)


def test_expurgo_respeita_a_janela(app):
    """Guarda o recente e apaga o antigo."""
    from datetime import datetime, timedelta
    from inventory.extensions import db
    from inventory.models.dvr_detection import DvrDetection
    from inventory.services import dvr_events

    from inventory.models.dvr import Dvr
    with app.app_context():
        # A deteccao tem FK para o DVR, entao o teste cria o seu proprio.
        d = Dvr(model="PYTEST-DVR", status="inativo")
        db.session.add(d)
        db.session.commit()
        did = d.id
        db.session.add_all([
            DvrDetection(dvr_id=did, channel=1, object_type="human",
                         started_at=datetime.now() - timedelta(days=400)),
            DvrDetection(dvr_id=did, channel=1, object_type="human",
                         started_at=datetime.now()),
        ])
        db.session.commit()

    app.config["DVR_DETECT_KEEP_DAYS"] = 90
    dvr_events.expurgar(app)

    with app.app_context():
        restantes = DvrDetection.query.filter_by(dvr_id=did).all()
        assert len(restantes) == 1, "deveria sobrar so a recente"
        DvrDetection.query.filter_by(dvr_id=did).delete()
        Dvr.query.filter_by(id=did).delete()
        db.session.commit()


def test_expurgo_desligavel(app):
    """DVR_DETECT_KEEP_DAYS=0 guarda tudo."""
    from inventory.services import dvr_events
    app.config["DVR_DETECT_KEEP_DAYS"] = 0
    assert dvr_events.expurgar(app) == 0
