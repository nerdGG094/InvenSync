"""Detecção inteligente (SMD): leitura do evento do DVR, estado ao vivo e histórico."""
import pytest

# Evento real capturado de um MHDX1232 (canal 9, humano).
EVENTO_HUMANO = (
    'Code=SmartMotionHuman;action=Start;index=8;data={\n'
    '   "object" : [\n'
    '      {\n'
    '         "Rect" : [ 733, 125, 793, 314 ],\n'
    '         "HumanID" : 0\n'
    '      }\n'
    '   ]\n'
    '}\n'
)
EVENTO_VEICULO = (
    'Code=SmartMotionVehicle;action=Start;index=0;data={\n'
    '   "object" : [ { "Rect" : [ 640, 67, 813, 244 ], "VehicleID" : 0 } ]\n'
    '}\n'
)
EVENTO_FIM = "Code=SmartMotionHuman;action=Stop;index=8"


@pytest.fixture
def dvr_det(app):
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.repositories import dvr_repo
    with app.app_context():
        d = dvr_repo.create_dvr(model="PYTEST-SMD", location="Portaria",
                                ip_address="10.0.0.80", admin_user="admin",
                                admin_password="x", channels=16)
        did = d.id
    yield did
    with app.app_context():
        obj = db.session.get(Dvr, did)
        if obj:
            db.session.delete(obj)
            db.session.commit()


def test_extrai_caixas_do_evento(app):
    from inventory.services import dvr_events
    assert dvr_events._rects_do_payload(EVENTO_HUMANO) == [[733, 125, 793, 314]]
    assert dvr_events._rects_do_payload(EVENTO_VEICULO) == [[640, 67, 813, 244]]
    assert dvr_events._rects_do_payload("Code=X;action=Start;index=1") == []
    # vários objetos no mesmo evento -> várias caixas
    varios = ('Code=SmartMotionHuman;action=Start;index=0;data={"object":['
              '{"HumanID":0,"Rect":[10,20,30,80]},'
              '{"HumanID":0,"Rect":[500,300,560,460]}]}')
    assert dvr_events._rects_do_payload(varios) == [[10, 20, 30, 80], [500, 300, 560, 460]]
    # não pode invadir o cabeçalho do evento seguinte, colado no mesmo bloco
    colado = EVENTO_HUMANO + "\r\n--myboundary\r\nContent-Length: 99"
    assert dvr_events._rects_do_payload(colado) == [[733, 125, 793, 314]]


def test_evento_vira_estado_ao_vivo_e_historico(app, dvr_det):
    from types import SimpleNamespace
    from inventory.extensions import db
    from inventory.models.dvr_detection import DvrDetection
    from inventory.services import dvr_events

    d = SimpleNamespace(id=dvr_det, location="Portaria", label=None, model="PYTEST-SMD")
    assert dvr_events._processar(app, d, EVENTO_HUMANO) is True

    # index=8 do DVR (base 0) é o canal 9 para o usuário
    vivos = dvr_events.ativos(dvr_det, ttl=60)
    assert 9 in vivos and len(vivos[9]) == 1
    assert vivos[9][0]["tipo"] == "human"
    assert vivos[9][0]["rect"] == [733, 125, 793, 314]

    with app.app_context():
        det = DvrDetection.query.filter_by(dvr_id=dvr_det, channel=9).first()
        assert det is not None and det.object_type == "human"
        assert det.rotulo == "Humano" and det.ended_at is None
        # escala 0-1023: pessoa alta e estreita (~5,9% x 18,5% do quadro)
        larg, alt = det.rect_pct[2], det.rect_pct[3]
        assert 4 < larg < 8 and 15 < alt < 22

    # o "Stop" limpa a tela e fecha o registro
    dvr_events._processar(app, d, EVENTO_FIM)
    assert 9 not in dvr_events.ativos(dvr_det, ttl=60)
    with app.app_context():
        det = DvrDetection.query.filter_by(dvr_id=dvr_det, channel=9).first()
        assert det.ended_at is not None
        db.session.query(DvrDetection).filter_by(dvr_id=dvr_det).delete()
        db.session.commit()


def test_deteccao_expira_sozinha(app, dvr_det):
    """Se a conexão cair sem o 'Stop', a caixa não pode ficar presa na tela."""
    from types import SimpleNamespace
    from inventory.extensions import db
    from inventory.models.dvr_detection import DvrDetection
    from inventory.services import dvr_events

    d = SimpleNamespace(id=dvr_det, location="Portaria", label=None, model="PYTEST-SMD")
    dvr_events._processar(app, d, EVENTO_VEICULO)
    assert dvr_events.ativos(dvr_det, ttl=60)          # vivo com prazo largo
    assert dvr_events.ativos(dvr_det, ttl=0.0) == {}   # e some com o prazo vencido
    with app.app_context():
        db.session.query(DvrDetection).filter_by(dvr_id=dvr_det).delete()
        db.session.commit()


def test_start_repetido_nao_duplica_historico(app, dvr_det):
    """O DVR reenvia 'Start' do mesmo objeto: isso é continuação, não registro novo."""
    from types import SimpleNamespace
    from inventory.extensions import db
    from inventory.models.dvr_detection import DvrDetection
    from inventory.services import dvr_events

    d = SimpleNamespace(id=dvr_det, location="Portaria", label=None, model="PYTEST-SMD")
    for _ in range(5):
        dvr_events._processar(app, d, EVENTO_HUMANO)
    with app.app_context():
        assert DvrDetection.query.filter_by(dvr_id=dvr_det, channel=9).count() == 1

    # objeto diferente no mesmo canal continua virando registro próprio
    dvr_events._processar(app, d, EVENTO_VEICULO.replace("index=0", "index=8"))
    with app.app_context():
        assert DvrDetection.query.filter_by(dvr_id=dvr_det, channel=9).count() == 2
        db.session.query(DvrDetection).filter_by(dvr_id=dvr_det).delete()
        db.session.commit()


def test_pessoas_lado_a_lado_nao_viram_uma_caixa_so(app):
    """Numa sala cheia as pessoas ficam coladas: só sobreposição real funde."""
    from inventory.services import dvr_events
    # duas pessoas encostadas, sem sobreposição -> objetos diferentes
    assert dvr_events._mesmo_objeto([100, 300, 160, 600], [165, 300, 225, 600]) is False
    # mesma pessoa um passo adiante -> caixas se cruzam bastante -> mesmo objeto
    assert dvr_events._mesmo_objeto([100, 300, 160, 600], [108, 302, 168, 602]) is True
    # do outro lado do quadro -> nunca é o mesmo
    assert dvr_events._mesmo_objeto([100, 300, 160, 600], [800, 300, 860, 600]) is False


def test_varios_objetos_no_mesmo_canal(app, dvr_det):
    """Sala cheia: várias pessoas E um veículo no mesmo canal, todos visíveis.

    A 1ª versão guardava UMA detecção por canal, então o evento seguinte apagava
    o anterior — com humano e veículo alternando, a pessoa nunca aparecia."""
    from types import SimpleNamespace
    from inventory.extensions import db
    from inventory.models.dvr_detection import DvrDetection
    from inventory.services import dvr_events

    d = SimpleNamespace(id=dvr_det, location="Portaria", label=None, model="PYTEST-SMD")
    molde = ('Code=SmartMotion{t};action=Start;index=4;data={{"object":['
             '{{"Rect":[{x1},{y1},{x2},{y2}]}}]}}')
    # três pessoas em pontos distintos do quadro
    for x in (100, 450, 800):
        dvr_events._processar(app, d, molde.format(t="Human", x1=x, y1=300, x2=x + 60, y2=600))
    # e um veículo no mesmo canal
    dvr_events._processar(app, d, molde.format(t="Vehicle", x1=20, y1=40, x2=300, y2=260))

    objs = dvr_events.ativos(dvr_det, ttl=60)[5]
    assert len(objs) == 4, f"esperava 4 objetos, veio {objs}"
    assert sum(1 for o in objs if o["tipo"] == "human") == 3
    assert sum(1 for o in objs if o["tipo"] == "vehicle") == 1

    # o "Stop" do veículo não pode derrubar as pessoas
    dvr_events._processar(app, d, "Code=SmartMotionVehicle;action=Stop;index=4")
    restantes = dvr_events.ativos(dvr_det, ttl=60)[5]
    assert len(restantes) == 3 and all(o["tipo"] == "human" for o in restantes)

    with app.app_context():
        db.session.query(DvrDetection).filter_by(dvr_id=dvr_det).delete()
        db.session.commit()


def test_endpoint_nao_consulta_o_banco(app, auth_client, dvr_det):
    """A página chama isto 1x/s: um SELECT aqui esgotava o pool de conexões."""
    from sqlalchemy import event
    from inventory.extensions import db

    disparos = []

    def registra(conn, cursor, sql, *a, **k):
        disparos.append(sql)

    with app.app_context():
        motor = db.engine
    event.listen(motor, "before_cursor_execute", registra)
    try:
        r = auth_client.get(f"/cftv/{dvr_det}/deteccoes")
    finally:
        event.remove(motor, "before_cursor_execute", registra)
    assert r.status_code == 200
    # Sobra só o SELECT do Flask-Login (usuário da sessão), que TODA rota
    # autenticada faz. O endpoint em si não pode tocar em dvr/dvr_detection.
    do_modulo = [s for s in disparos if "dvr" in s.lower()]
    assert do_modulo == [], f"endpoint consultou o banco: {do_modulo}"
    assert len(disparos) <= 1, f"consultas demais para um poll de 1s: {disparos}"


def test_endpoint_devolve_caixa_em_porcentagem(app, auth_client, dvr_det):
    from types import SimpleNamespace
    from inventory.extensions import db
    from inventory.models.dvr_detection import DvrDetection
    from inventory.services import dvr_events

    d = SimpleNamespace(id=dvr_det, location="Portaria", label=None, model="PYTEST-SMD")
    dvr_events._processar(app, d, EVENTO_VEICULO)
    j = auth_client.get(f"/cftv/{dvr_det}/deteccoes").get_json()
    canal = j["ativos"]["1"]
    assert isinstance(canal, list) and len(canal) == 1
    assert canal[0]["tipo"] == "vehicle"
    cx = canal[0]["caixa"]
    # [640,67,813,244] / 1024 -> começa em 62.5%, 6.54%; 16.9% x 17.29%
    assert cx["left"] == pytest.approx(62.5, abs=0.1)
    assert cx["top"] == pytest.approx(6.54, abs=0.1)
    assert cx["width"] == pytest.approx(16.89, abs=0.1)
    assert cx["height"] == pytest.approx(17.29, abs=0.1)
    with app.app_context():
        db.session.query(DvrDetection).filter_by(dvr_id=dvr_det).delete()
        db.session.commit()


def test_historico_abre_e_filtra(app, auth_client, dvr_det):
    from types import SimpleNamespace
    from inventory.extensions import db
    from inventory.models.dvr_detection import DvrDetection
    from inventory.services import dvr_events

    d = SimpleNamespace(id=dvr_det, location="Portaria", label=None, model="PYTEST-SMD")
    dvr_events._processar(app, d, EVENTO_HUMANO)
    dvr_events._processar(app, d, EVENTO_VEICULO)

    def corpo_da_tabela(html):
        """Só as linhas — a página inteira sempre cita os dois tipos no filtro."""
        return html.split("<tbody>")[1].split("</tbody>")[0] if "<tbody>" in html else ""

    r = auth_client.get("/cftv/deteccoes")
    assert r.status_code == 200 and "Portaria" in r.get_data(as_text=True)
    todos = corpo_da_tabela(r.get_data(as_text=True))
    assert "Humano" in todos and "Veículo" in todos

    filtrado = corpo_da_tabela(
        auth_client.get(f"/cftv/deteccoes?dvr={dvr_det}&tipo=vehicle").get_data(as_text=True))
    assert "Veículo" in filtrado and "Humano" not in filtrado
    with app.app_context():
        db.session.query(DvrDetection).filter_by(dvr_id=dvr_det).delete()
        db.session.commit()


def test_deteccoes_bloqueia_nao_admin(app, common_client, dvr_det):
    assert common_client.get("/cftv/deteccoes").status_code in (403, 302)
    assert common_client.get(f"/cftv/{dvr_det}/deteccoes").status_code in (403, 302)
