"""Tomadas inteligentes (Tuya/NeoAvant): CRUD, chave cifrada e falha graciosa."""
import pytest

from inventory.extensions import db
from inventory.models.smart_plug import SmartPlug
from inventory.services import crypto

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        SmartPlug.query.filter(SmartPlug.name.like(f"{MARK}%")).delete()
        db.session.commit()


def test_list_admin_ok(auth_client):
    assert auth_client.get("/tomadas").status_code == 200


def test_create_encrypts_local_key(app, auth_client):
    r = auth_client.post("/tomadas/new", data={
        "name": f"{MARK} Tomada", "device_id": "bf123abc", "ip_address": "192.168.0.199",
        "local_key": "segredo-local", "version": "3.3", "switch_dp": "1", "is_active": "y",
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        p = SmartPlug.query.filter_by(name=f"{MARK} Tomada").first()
        assert p is not None
        assert p.local_key and p.local_key != "segredo-local"    # cifrada em repouso
        assert crypto.decrypt(p.local_key) == "segredo-local"    # decifra de volta


def test_toggle_without_device_is_graceful(app, auth_client):
    with app.app_context():
        p = SmartPlug(name=f"{MARK} SemRede", device_id="bf1", ip_address=None, local_key=None)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    r = auth_client.post(f"/tomadas/{pid}/toggle", data={"on": "1"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is False and j.get("error")   # não estoura; devolve erro amigável
