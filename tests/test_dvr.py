"""Módulo CFTV/DVR: cifragem da senha, status/senha e acesso admin-only."""


def test_senha_cifrada_em_repouso(app):
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.repositories import dvr_repo
    from inventory.services import crypto
    with app.app_context():
        d = dvr_repo.create_dvr(model="PYTEST-DVR", ip_address="10.0.0.60",
                                admin_user="admin", admin_password="cftv123", channels=8)
        did = d.id
        raw = db.session.get(Dvr, did).admin_password
        assert raw != "cftv123" and crypto.looks_encrypted(raw)
        assert crypto.decrypt(raw) == "cftv123"
        db.session.delete(db.session.get(Dvr, did))
        db.session.commit()


def test_editar_senha_em_branco_mantem(app):
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.repositories import dvr_repo
    from inventory.services import crypto
    with app.app_context():
        d = dvr_repo.create_dvr(model="PYTEST-DVR2", admin_password="abc123")
        did = d.id
        dvr_repo.update_dvr(d, model="PYTEST-DVR2", admin_password=None, location="Portaria")
        d2 = db.session.get(Dvr, did)
        assert crypto.decrypt(d2.admin_password) == "abc123" and d2.location == "Portaria"
        db.session.delete(d2)
        db.session.commit()


def test_senha_endpoint_revela(app, auth_client):
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.repositories import dvr_repo
    with app.app_context():
        d = dvr_repo.create_dvr(model="PYTEST-REVEAL", ip_address="10.0.0.61", web_port=8080,
                                admin_user="adm", admin_password="s3cr3t")
        did = d.id
    j = auth_client.get(f"/cftv/{did}/senha").get_json()
    assert j["password"] == "s3cr3t" and j["user"] == "adm"
    assert j["url"] == "http://10.0.0.61:8080"     # porta custom no url
    with app.app_context():
        db.session.delete(db.session.get(Dvr, did))
        db.session.commit()


def test_status_offline_gracioso(app, auth_client):
    from inventory.extensions import db
    from inventory.models.dvr import Dvr
    from inventory.repositories import dvr_repo
    with app.app_context():
        d = dvr_repo.create_dvr(model="PYTEST-OFF", ip_address="192.0.2.200")  # TEST-NET, nunca responde
        did = d.id
    j = auth_client.get(f"/cftv/{did}/status").get_json()
    assert j["online"] is False
    with app.app_context():
        db.session.delete(db.session.get(Dvr, did))
        db.session.commit()


def test_cftv_bloqueia_nao_admin(app, common_client):
    assert common_client.get("/cftv").status_code in (403, 302)
