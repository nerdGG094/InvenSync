"""Painel de roteadores: cifragem em repouso, sondagem e endpoints de acesso."""
from inventory.services import router_ctl


def test_auth_url_encodes_credentials():
    url = router_ctl.auth_url("192.168.0.106", "admin", "p@ss w/d")
    assert url == "http://admin:p%40ss%20w%2Fd@192.168.0.106"


def test_base_url_normaliza():
    assert router_ctl.base_url("10.0.0.1") == "http://10.0.0.1"
    assert router_ctl.base_url("https://10.0.0.1") == "https://10.0.0.1"
    assert router_ctl.base_url("") == ""


def test_probe_offline_gracioso():
    """IP inalcançável -> offline rápido, sem exceção."""
    d = router_ctl.probe("192.0.2.123", timeout=0.5)  # TEST-NET-1, nunca responde
    assert d["online"] is False and d["auth_kind"] == "offline"


def test_probe_sem_ip():
    d = router_ctl.probe("")
    assert d["online"] is False and d["auth_kind"] == "sem-ip"


def test_senha_cifrada_em_repouso(app):
    """create_router cifra a senha admin; no banco não fica em texto puro."""
    from inventory.extensions import db
    from inventory.models.router import Router
    from inventory.repositories import router_repo
    from inventory.services import crypto
    with app.app_context():
        r = router_repo.create_router(model="PYTEST-RT", ip_address="10.9.9.9",
                                       admin_user="root", admin_password="segredo123")
        rid = r.id
        raw = db.session.get(Router, rid).admin_password
        assert raw != "segredo123"
        assert crypto.looks_encrypted(raw)
        assert crypto.decrypt(raw) == "segredo123"
        db.session.delete(db.session.get(Router, rid))
        db.session.commit()


def test_editar_em_branco_mantem_senha(app):
    """Senha em branco ao editar não apaga a atual."""
    from inventory.extensions import db
    from inventory.models.router import Router
    from inventory.repositories import router_repo
    from inventory.services import crypto
    with app.app_context():
        r = router_repo.create_router(model="PYTEST-RT2", admin_password="abc123")
        rid = r.id
        router_repo.update_router(r, model="PYTEST-RT2", admin_password=None, label="novo")
        r2 = db.session.get(Router, rid)
        assert crypto.decrypt(r2.admin_password) == "abc123" and r2.label == "novo"
        db.session.delete(r2)
        db.session.commit()


def test_senha_endpoint_revela_decifrado(app, auth_client):
    from inventory.extensions import db
    from inventory.models.router import Router
    from inventory.repositories import router_repo
    with app.app_context():
        r = router_repo.create_router(model="PYTEST-REVEAL", admin_user="adm",
                                      admin_password="topsecret")
        rid = r.id
    j = auth_client.get(f"/routers/{rid}/senha?tipo=admin").get_json()
    assert j["password"] == "topsecret" and j["user"] == "adm"
    with app.app_context():
        db.session.delete(db.session.get(Router, rid))
        db.session.commit()


def test_entrar_redireciona_com_credenciais(app, auth_client):
    from inventory.extensions import db
    from inventory.models.router import Router
    from inventory.repositories import router_repo
    with app.app_context():
        r = router_repo.create_router(model="PYTEST-ENTRAR", ip_address="10.5.5.5",
                                      admin_user="adm", admin_password="pw1")
        rid = r.id
    resp = auth_client.get(f"/routers/{rid}/entrar", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "http://adm:pw1@10.5.5.5"
    with app.app_context():
        db.session.delete(db.session.get(Router, rid))
        db.session.commit()


def test_painel_bloqueia_nao_admin(app, common_client):
    from inventory.extensions import db
    from inventory.models.router import Router
    from inventory.repositories import router_repo
    with app.app_context():
        r = router_repo.create_router(model="PYTEST-403", ip_address="10.1.1.1")
        rid = r.id
    # usuário comum não acessa o painel nem os segredos
    assert common_client.get(f"/routers/{rid}/senha").status_code in (403, 302)
    assert common_client.get("/routers").status_code in (403, 302)
    with app.app_context():
        db.session.delete(db.session.get(Router, rid))
        db.session.commit()
