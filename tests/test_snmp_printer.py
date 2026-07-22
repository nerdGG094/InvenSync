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


def test_decode_error_bitmap():
    """hrPrinterDetectedErrorState: bitmap -> lista de alertas legíveis."""
    assert sp._decode_errors(b"\x00") == []                 # tudo ok
    # bit 0 (mais significativo) = lowPaper
    r = sp._decode_errors(bytes([0b10000000]))
    assert [a["key"] for a in r] == ["lowPaper"]
    # bit 3 = noToner (danger), bit 5 = jammed (danger)
    r2 = {a["key"]: a["level"] for a in sp._decode_errors(bytes([0b00010100]))}
    assert r2.get("noToner") == "danger" and r2.get("jammed") == "danger"


def test_printer_monitor_history_and_single_alert(app, monkeypatch):
    """Coleta grava histórico e avisa UMA vez quando o toner cai; ao recuperar,
    re-arma e volta a avisar."""
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.printer_reading import PrinterReading
    from inventory.services import printer_monitor

    with app.app_context():
        app.config["PRINTER_SUPPLY_ALERT_PCT"] = 10
        printer_monitor._alerted.clear()
        m = Machine(kind="impressora", model="PYTEST-PR", ip_address="10.0.0.9",
                    sector="TI", is_active=True)
        db.session.add(m)
        db.session.commit()
        mid = m.id

        avisos = {"n": 0}
        monkeypatch.setattr("inventory.services.mailer.notify_ti",
                            lambda *a, **k: avisos.__setitem__("n", avisos["n"] + 1))

        estado = {"toner": 8}   # começa baixo
        monkeypatch.setattr("inventory.services.snmp_printer.query",
                            lambda ip, **k: {"ok": True, "pages": 100,
                                             "toner_pct": estado["toner"], "supplies": []})

        lidas, av = printer_monitor.collect_once(app)
        assert lidas == 1 and av == 1 and avisos["n"] == 1
        assert PrinterReading.query.filter_by(machine_id=mid).count() == 1

        # segunda coleta ainda baixo -> não repete o aviso
        _, av2 = printer_monitor.collect_once(app)
        assert av2 == 0 and avisos["n"] == 1

        # trocou o toner (subiu bem acima do limite) -> re-arma
        estado["toner"] = 100
        printer_monitor.collect_once(app)
        estado["toner"] = 5
        _, av3 = printer_monitor.collect_once(app)
        assert av3 == 1 and avisos["n"] == 2

        PrinterReading.query.filter_by(machine_id=mid).delete()
        Machine.query.filter_by(id=mid).delete()
        db.session.commit()


def test_printers_report_computes_pages_in_date_range(app, auth_client):
    """Consumo no intervalo = contador do fim − contador do início."""
    from datetime import datetime, timedelta
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.printer_reading import PrinterReading

    with app.app_context():
        m = Machine(kind="impressora", model="PYTEST-RPT", ip_address="10.0.0.7", sector="TI")
        db.session.add(m)
        db.session.commit()
        mid = m.id
        base = datetime.now()
        db.session.add(PrinterReading(machine_id=mid, pages=100000,
                                      taken_at=base - timedelta(days=6)))
        db.session.add(PrinterReading(machine_id=mid, pages=112345,
                                      taken_at=base - timedelta(days=1)))
        db.session.commit()

    r = auth_client.get("/machines/impressoras/consumo?dias=7")
    assert r.status_code == 200
    assert b"12.345" in r.data          # 112345 - 100000 = 12345 (pt-BR)

    with app.app_context():
        PrinterReading.query.filter_by(machine_id=mid).delete()
        Machine.query.filter_by(id=mid).delete()
        db.session.commit()


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
