"""CFTV em tempo real: geração do go2rtc.yaml e escolha do player na página."""
import pytest


@pytest.fixture
def dvr_teste(app):
    """DVR descartável com 3 canais e senha cifrada."""
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.repositories import dvr_repo
    with app.app_context():
        d = dvr_repo.create_dvr(model="PYTEST-G2", location="Portaria",
                                ip_address="10.0.0.70", admin_user="admin",
                                admin_password="s3nh@/dvr", channels=3)
        did = d.id
    yield did
    with app.app_context():
        obj = db.session.get(Dvr, did)
        if obj:
            db.session.delete(obj)
            db.session.commit()


def test_desligado_sem_url(app):
    """Sem GO2RTC_URL o módulo fica inerte (a página cai no snapshot)."""
    from inventory.services import go2rtc
    with app.app_context():
        app.config["GO2RTC_URL"] = ""
        assert go2rtc.enabled() is False
        assert go2rtc.base_url() == ""
        assert go2rtc.probe() == {"enabled": False, "online": False, "url": "",
                                  "streams": 0, "version": "", "names": []}


def test_yaml_um_stream_por_canal(app, dvr_teste):
    from inventory.models.dvr import Dvr
    from inventory.extensions import db
    from inventory.services import go2rtc
    with app.app_context():
        app.config["GO2RTC_TRANSCODE"] = False
        d = db.session.get(Dvr, dvr_teste)
        texto, n = go2rtc.build_config([d])
        assert n == 3
        assert f"  dvr{d.id}_ch1: " in texto and f"  dvr{d.id}_ch3: " in texto
        # senha decifrada e PERCENT-ENCODED (tem "@" e "/", que quebrariam a URL)
        assert "s3nh%40%2Fdvr@10.0.0.70:554" in texto
        # caminho conferido nos DVRs: /cam/realmonitor (singular; "cams" dá 404)
        # e stream principal (subtype=0), que é o HD 720p.
        assert "/cam/realmonitor?channel=1&subtype=0" in texto
        # a prévia da tela nunca mostra a senha
        mascarado, _ = go2rtc.build_config([d], mask=True)
        assert "s3nh" not in mascarado and go2rtc.MASK in mascarado


def test_yaml_transcode_para_h264(app, dvr_teste, tmp_path):
    """Com transcode, cada canal ganha a 2ª fonte ffmpeg (o HD é H.265)."""
    from inventory.models.dvr import Dvr
    from inventory.extensions import db
    from inventory.services import go2rtc
    ff = tmp_path / "ffmpeg.exe"
    ff.write_bytes(b"")
    with app.app_context():
        app.config["GO2RTC_TRANSCODE"] = True
        app.config["GO2RTC_FFMPEG"] = str(ff)
        d = db.session.get(Dvr, dvr_teste)
        texto, n = go2rtc.build_config([d], mask=True)
        assert n == 3
        assert f"  dvr{d.id}_ch2:\n" in texto                       # chave + lista
        assert f'    - "ffmpeg:dvr{d.id}_ch2#video=h264"' in texto  # 2ª fonte
        assert "ffmpeg:\n  bin: " in texto                          # binário declarado
        # sem transcode volta a ser uma linha só, sem ffmpeg
        app.config["GO2RTC_TRANSCODE"] = False
        simples, _ = go2rtc.build_config([d], mask=True)
        assert "ffmpeg" not in simples and f"  dvr{d.id}_ch2: " in simples


def test_yaml_ignora_inativo_e_sem_canais(app, dvr_teste):
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.repositories import dvr_repo
    from inventory.services import go2rtc
    with app.app_context():
        d = db.session.get(Dvr, dvr_teste)
        assert go2rtc.eligible([d]) == [d]
        d.channels = None
        assert go2rtc.eligible([d]) == []
        d.channels = 3
        d.status = "inativo"
        assert go2rtc.eligible([d]) == []
        d.status = "em_uso"
        d.ip_address = None
        assert go2rtc.eligible([d]) == []
        db.session.rollback()
        assert dvr_repo.get_dvr(dvr_teste) is not None


def test_gerar_arquivo_pela_tela(app, auth_client, dvr_teste, tmp_path):
    from inventory.services import go2rtc
    destino = tmp_path / "go2rtc" / "go2rtc.yaml"
    app.config["GO2RTC_CONFIG"] = str(destino)
    r = auth_client.post("/cftv/go2rtc/gerar")
    assert r.status_code in (301, 302, 303)
    assert destino.is_file()
    conteudo = destino.read_text(encoding="utf-8")
    assert "streams:" in conteudo and f"dvr{dvr_teste}_ch2:" in conteudo
    with app.app_context():
        st = go2rtc.config_status()
        assert st["exists"] and st["streams"] >= 3


def test_player_so_para_streams_conhecidos(app, dvr_teste):
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.services import go2rtc
    with app.app_context():
        app.config["GO2RTC_URL"] = "192.168.0.54:1984"      # sem esquema -> http://
        d = db.session.get(Dvr, dvr_teste)
        assert go2rtc.base_url() == "http://192.168.0.54:1984"
        url = go2rtc.player_url(d, 2)
        assert url.startswith("http://192.168.0.54:1984/stream.html?src=dvr")
        assert "mode=webrtc,mse" in url
        # só entram os canais que o go2rtc realmente publica
        conhecidos = [go2rtc.stream_name(d, 1), go2rtc.stream_name(d, 3)]
        assert sorted(go2rtc.player_urls(d, [1, 2, 3], conhecidos)) == [1, 3]


def test_pagina_cameras_avisa_quando_offline(app, auth_client, dvr_teste):
    """go2rtc configurado mas fora do ar: página abre em snapshot, sem quebrar."""
    app.config["GO2RTC_URL"] = "http://192.0.2.201:1984"    # TEST-NET, nunca responde
    app.config["GO2RTC_TIMEOUT"] = 0.4
    r = auth_client.get(f"/cftv/{dvr_teste}/cameras")
    assert r.status_code == 200
    corpo = r.get_data(as_text=True)
    assert "var LIVE_OK = false;" in corpo
    assert "não respondeu" in corpo.lower() or "snapshot" in corpo


def test_go2rtc_bloqueia_nao_admin(app, common_client):
    assert common_client.get("/cftv/go2rtc").status_code in (403, 302)
    assert common_client.post("/cftv/go2rtc/gerar").status_code in (403, 302)
