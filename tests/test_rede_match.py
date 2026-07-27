"""MAC/hostname no cadastro + match no módulo Rede + status ao vivo dos PCs."""
from inventory.services import net_scan


def test_norm_mac_normaliza():
    from inventory.routes.machines import _norm_mac
    assert _norm_mac("1C:39:47:0E:11:99") == "1c-39-47-0e-11-99"
    assert _norm_mac("1c3947 0e1199") == "1c-39-47-0e-11-99"
    assert _norm_mac("") is None


def test_netbios_regex():
    assert net_scan._NB_RE.search("  COMERCIAL1     <00>  UNIQUE      Registered")
    assert not net_scan._NB_RE.search("  GRUPO          <00>  GROUP       Registered")


def test_active_set(monkeypatch):
    monkeypatch.setattr(net_scan, "_read_arp",
                        lambda: [("192.168.0.10", "1c-39-47-0e-11-99"),
                                 ("224.0.0.1", "01-00-5e-00-00-01")])  # multicast dropado
    macs, ips = net_scan.active_set()
    assert macs == {"1c-39-47-0e-11-99"} and ips == {"192.168.0.10"}


def test_form_salva_mac_normalizado(app, auth_client):
    """O cadastro guarda o MAC normalizado (minúsculo com hífens)."""
    from inventory.extensions import db
    from inventory.models.machine import Machine
    r = auth_client.post("/machines/new", data={
        "kind": "notebook", "model": "PYTEST-MAC", "mac_address": "AA:BB:CC:DD:EE:FF",
        "hostname": "PC-TESTE", "ip_address": "DHCP"}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        m = Machine.query.filter_by(model="PYTEST-MAC").first()
        assert m and m.mac_address == "aa-bb-cc-dd-ee-ff" and m.hostname == "PC-TESTE"
        db.session.delete(m)
        db.session.commit()


def test_rede_match_por_mac_e_vincular(app, auth_client, monkeypatch):
    from inventory.extensions import db
    from inventory.models.machine import Machine
    with app.app_context():
        m = Machine(kind="computador", model="PYTEST-NET", mac_address="1c-39-47-0e-11-99")
        db.session.add(m)
        db.session.commit()
        mid = m.id
    # dispositivo com esse MAC deve casar mesmo com IP diferente (DHCP)
    monkeypatch.setattr(net_scan, "scan", lambda app, sweep=False: [
        {"ip": "192.168.0.99", "mac": "1c-39-47-0e-11-99", "name": ""}])
    j = auth_client.get("/rede/scan").get_json()
    assert j["cadastrados"] == 1 and j["dispositivos"][0]["machine_id"] == mid
    assert j["dispositivos"][0]["mac_salvo"] is True

    # vincular um MAC novo a uma máquina sem MAC
    with app.app_context():
        m2 = Machine(kind="computador", model="PYTEST-NET2")
        db.session.add(m2)
        db.session.commit()
        mid2 = m2.id
    r = auth_client.post("/rede/vincular", data={
        "machine_id": mid2, "mac": "aa-bb-cc-11-22-33", "host": "PC2"})
    assert r.get_json()["ok"] is True
    with app.app_context():
        m2 = db.session.get(Machine, mid2)
        assert m2.mac_address == "aa-bb-cc-11-22-33" and m2.hostname == "PC2"
        db.session.delete(m2)
        db.session.delete(db.session.get(Machine, mid))
        db.session.commit()


def test_rede_ativos_endpoint(app, auth_client, monkeypatch):
    monkeypatch.setattr(net_scan, "active_set",
                        lambda: ({"1c-39-47-0e-11-99"}, {"192.168.0.10"}))
    j = auth_client.get("/machines/rede-ativos").get_json()
    assert "1c-39-47-0e-11-99" in j["macs"] and "192.168.0.10" in j["ips"]
