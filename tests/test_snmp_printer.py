"""Leitura SNMP de impressoras: decodificação e cálculo de percentuais."""
import pytest

from inventory.services import snmp_printer as sp


def test_decode_brother_maintenance_blob():
    """Formato <item><tipo><tam><valor>; 0x81 é o % de toner (validado em campo)."""
    blob = bytes.fromhex("63010400000001810104000000508601040000000aff")
    d = sp._decode_brother(blob)
    assert d[0x81] == 80          # toner restante
    assert d[0x63] == 1
    assert d[0x86] == 10
    assert 0xFF not in d          # terminador não vira item


def test_query_sem_ip_nao_levanta():
    r = sp.query("")
    assert r["ok"] is False and r["error"]


def test_query_host_inexistente_e_gracioso():
    """IP inalcançável deve devolver ok=False rapidamente, sem exceção."""
    r = sp.query("192.0.2.123", timeout=0.5)   # faixa TEST-NET-1, nunca responde
    assert r["ok"] is False and r["error"]


def test_snmp_route_recusa_maquina_que_nao_e_impressora(app, auth_client):
    from inventory.extensions import db
    from inventory.models.machine import Machine
    with app.app_context():
        m = Machine(kind="computador", model="PYTEST-PC", ip_address="10.0.0.1")
        db.session.add(m)
        db.session.commit()
        mid = m.id
    r = auth_client.get(f"/machines/{mid}/snmp")
    assert r.status_code == 400 and r.get_json()["ok"] is False
    with app.app_context():
        Machine.query.filter_by(id=mid).delete()
        db.session.commit()
