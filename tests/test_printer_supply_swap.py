"""Baixa automática de toner/cilindro na troca (nível subiu de baixo p/ cheio)."""


def _mk_product(db, sku, segment="suprimento", stock_in=0):
    from inventory.models.product import Product
    from inventory.models.movement import StockMovement
    p = Product(sku=sku, name=f"Material {sku}", segment=segment)
    db.session.add(p)
    db.session.commit()
    if stock_in:
        db.session.add(StockMovement(product_id=p.id, movement_type="IN", quantity=stock_in))
        db.session.commit()
    return p


def _reset(pm):
    pm._alerted.clear()
    pm._last_pct.clear()


def test_troca_da_baixa_de_uma_unidade(app, monkeypatch):
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.movement import StockMovement
    from inventory.models.printer_reading import PrinterReading
    from inventory.models.product import Product
    from inventory.services import printer_monitor
    from inventory.repositories import product_repo

    with app.app_context():
        _reset(printer_monitor)
        toner = _mk_product(db, "TN-PYTEST", stock_in=3)
        m = Machine(kind="impressora", model="PR-SWAP", ip_address="10.0.0.20",
                    sector="TI", is_active=True, toner_product_id=toner.id)
        db.session.add(m)
        db.session.commit()
        mid, pid = m.id, toner.id

        estado = {"toner": 5}
        monkeypatch.setattr("inventory.services.snmp_printer.query",
                            lambda ip, **k: {"ok": True, "pages": 100,
                                             "toner_pct": estado["toner"], "supplies": []})

        printer_monitor.collect_once(app)          # leitura baixa (5%) — sem troca ainda
        estado["toner"] = 100                       # trocou o toner
        printer_monitor.collect_once(app)          # subiu p/ cheio -> baixa

        saidas = (StockMovement.query
                  .filter_by(product_id=pid, movement_type="OUT").all())
        assert len(saidas) == 1 and saidas[0].quantity == 1
        assert product_repo.current_stock(db.session.get(Product, pid)) == 2  # 3 IN - 1 OUT

        # limpeza
        StockMovement.query.filter_by(product_id=pid).delete()
        PrinterReading.query.filter_by(machine_id=mid).delete()
        db.session.delete(db.session.get(Machine, mid))
        db.session.delete(db.session.get(Product, pid))
        db.session.commit()


def test_troca_de_20_para_100_dispara(app, monkeypatch):
    """Cenário do RH: toner em 20% (acima do limite) trocado -> sobe p/ 100%.
    Salto grande (+80) deve registrar a baixa."""
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.movement import StockMovement
    from inventory.models.printer_reading import PrinterReading
    from inventory.models.product import Product
    from inventory.services import printer_monitor

    with app.app_context():
        _reset(printer_monitor)
        toner = _mk_product(db, "TN-RH", stock_in=2)
        m = Machine(kind="impressora", model="PR-RH", ip_address="10.0.0.30",
                    sector="RH", is_active=True, toner_product_id=toner.id)
        db.session.add(m)
        db.session.commit()
        mid, pid = m.id, toner.id

        estado = {"toner": 20}
        monkeypatch.setattr("inventory.services.snmp_printer.query",
                            lambda ip, **k: {"ok": True, "pages": 10,
                                             "toner_pct": estado["toner"], "supplies": []})
        printer_monitor.collect_once(app)   # 20%
        estado["toner"] = 100
        printer_monitor.collect_once(app)   # trocou -> 100%

        assert StockMovement.query.filter_by(product_id=pid, movement_type="OUT").count() == 1

        StockMovement.query.filter_by(product_id=pid).delete()
        PrinterReading.query.filter_by(machine_id=mid).delete()
        db.session.delete(db.session.get(Machine, mid))
        db.session.delete(db.session.get(Product, pid))
        db.session.commit()


def test_subida_pequena_nao_dispara(app, monkeypatch):
    """Variação pequena (ex.: 60%->85%, salto 25 < 40) NÃO conta como troca."""
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.movement import StockMovement
    from inventory.models.printer_reading import PrinterReading
    from inventory.models.product import Product
    from inventory.services import printer_monitor

    with app.app_context():
        _reset(printer_monitor)
        toner = _mk_product(db, "TN-NOISE", stock_in=2)
        m = Machine(kind="impressora", model="PR-NOISE", ip_address="10.0.0.31",
                    sector="TI", is_active=True, toner_product_id=toner.id)
        db.session.add(m)
        db.session.commit()
        mid, pid = m.id, toner.id

        estado = {"toner": 60}
        monkeypatch.setattr("inventory.services.snmp_printer.query",
                            lambda ip, **k: {"ok": True, "pages": 10,
                                             "toner_pct": estado["toner"], "supplies": []})
        printer_monitor.collect_once(app)   # 60%
        estado["toner"] = 85
        printer_monitor.collect_once(app)   # +25 -> não é troca

        assert StockMovement.query.filter_by(product_id=pid, movement_type="OUT").count() == 0

        StockMovement.query.filter_by(product_id=pid).delete()
        PrinterReading.query.filter_by(machine_id=mid).delete()
        db.session.delete(db.session.get(Machine, mid))
        db.session.delete(db.session.get(Product, pid))
        db.session.commit()


def test_troca_com_estoque_zero_avisa_ti(app, monkeypatch):
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.movement import StockMovement
    from inventory.models.printer_reading import PrinterReading
    from inventory.models.product import Product
    from inventory.services import printer_monitor

    with app.app_context():
        _reset(printer_monitor)
        cil = _mk_product(db, "DR-PYTEST", stock_in=0)  # saldo zero
        m = Machine(kind="impressora", model="PR-ZERO", ip_address="10.0.0.21",
                    sector="TI", is_active=True, drum_product_id=cil.id)
        db.session.add(m)
        db.session.commit()
        mid, pid = m.id, cil.id

        avisos = []
        monkeypatch.setattr("inventory.services.mailer.notify_ti",
                            lambda subj, body=None, *a, **k: avisos.append(subj))
        estado = {"drum": 8}
        monkeypatch.setattr("inventory.services.snmp_printer.query",
                            lambda ip, **k: {"ok": True, "pages": None, "toner_pct": None,
                                             "supplies": [{"pct": estado["drum"], "desc": "drum unit"}]})

        printer_monitor.collect_once(app)
        estado["drum"] = 95
        printer_monitor.collect_once(app)

        saidas = StockMovement.query.filter_by(product_id=pid, movement_type="OUT").all()
        assert len(saidas) == 1
        assert any("Estoque zerado" in s for s in avisos)

        StockMovement.query.filter_by(product_id=pid).delete()
        PrinterReading.query.filter_by(machine_id=mid).delete()
        db.session.delete(db.session.get(Machine, mid))
        db.session.delete(db.session.get(Product, pid))
        db.session.commit()


def test_sem_material_vinculado_nao_movimenta(app, monkeypatch):
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.movement import StockMovement
    from inventory.models.printer_reading import PrinterReading
    from inventory.services import printer_monitor

    with app.app_context():
        _reset(printer_monitor)
        antes = StockMovement.query.count()
        m = Machine(kind="impressora", model="PR-NOLINK", ip_address="10.0.0.22",
                    is_active=True)  # sem toner/cilindro vinculado
        db.session.add(m)
        db.session.commit()
        mid = m.id

        estado = {"toner": 5}
        monkeypatch.setattr("inventory.services.snmp_printer.query",
                            lambda ip, **k: {"ok": True, "pages": None,
                                             "toner_pct": estado["toner"], "supplies": []})
        printer_monitor.collect_once(app)
        estado["toner"] = 100
        printer_monitor.collect_once(app)

        assert StockMovement.query.count() == antes  # nada movimentado

        PrinterReading.query.filter_by(machine_id=mid).delete()
        db.session.delete(db.session.get(Machine, mid))
        db.session.commit()


def test_form_impressora_mostra_suprimentos(app, auth_client):
    """A tela de nova máquina (impressora) traz os comboboxes de suprimento."""
    r = auth_client.get("/machines/new?kind=impressora")
    assert r.status_code == 200
    assert "Suprimentos da impressora".encode() in r.data
    assert b"tonerProd" in r.data and b"drumProd" in r.data
