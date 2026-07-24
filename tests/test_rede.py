"""Descoberta de rede (ARP): parse/filtro do serviço e acesso admin-only."""
from inventory.services import net_scan


def test_arp_parse_e_filtro():
    """Extrai IP+MAC do texto do arp e descarta multicast/broadcast/link-local."""
    texto = (
        "  192.168.0.10          1c-39-47-0e-11-99     dinamico\n"
        "  192.168.1.25          1c-c1-de-2a-52-7c     dinamico\n"
        "  169.254.8.225         70-cd-0d-07-9e-f5     dinamico\n"   # link-local
        "  224.0.0.22            01-00-5e-00-00-16     estatico\n"   # multicast
        "  192.168.0.255         ff-ff-ff-ff-ff-ff     estatico\n"  # broadcast
    )
    pares = net_scan._ARP_RE.findall(texto)
    validos = [(ip, mac.lower().replace(":", "-")) for ip, mac in pares
               if net_scan._e_dispositivo(ip, mac.lower().replace(":", "-"))]
    ips = [ip for ip, _ in validos]
    assert ips == ["192.168.0.10", "192.168.1.25"]


def test_scan_nunca_levanta(app, monkeypatch):
    """scan() é best-effort: erro ao ler ARP -> lista vazia, sem exceção."""
    monkeypatch.setattr(net_scan, "_read_arp", lambda: (_ for _ in ()).throw(OSError("x")))
    with app.app_context():
        assert net_scan.scan(app) == []


def test_scan_monta_dispositivos(app, monkeypatch):
    monkeypatch.setattr(net_scan, "_read_arp",
                        lambda: [("192.168.0.10", "1c-39-47-0e-11-99"),
                                 ("192.168.0.10", "1c-39-47-0e-11-99"),   # dup
                                 ("224.0.0.1", "01-00-5e-00-00-01")])     # multicast
    monkeypatch.setattr(net_scan, "_rdns", lambda ip: "Comercial1.palazzo.local")
    with app.app_context():
        devs = net_scan.scan(app)
    assert len(devs) == 1
    assert devs[0]["ip"] == "192.168.0.10" and devs[0]["name"].startswith("Comercial1")


def test_pagina_rede_abre_instantanea(app, auth_client):
    """A página abre sem escanear (o scan é sob demanda por AJAX)."""
    r = auth_client.get("/rede")
    assert r.status_code == 200 and b"Escanear rede" in r.data


def test_scan_endpoint_json_e_bloqueio(app, auth_client, common_client, monkeypatch):
    monkeypatch.setattr(net_scan, "scan", lambda app, sweep=False: [
        {"ip": "192.168.0.10", "mac": "1c-39-47-0e-11-99", "name": "Comercial1.palazzo.local"}])
    j = auth_client.get("/rede/scan").get_json()
    assert j["total"] == 1 and j["dispositivos"][0]["ip"] == "192.168.0.10"
    assert j["dispositivos"][0]["host"] == "Comercial1"
    assert common_client.get("/rede/scan").status_code in (403, 302)
