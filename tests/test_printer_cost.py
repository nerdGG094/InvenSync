"""#3 custo de impressão por setor: baixa de toner grava setor+custo e soma no relatório."""


def test_baixa_grava_setor_e_custo(app, monkeypatch):
    from inventory.extensions import db
    from inventory.models.machine import Machine
    from inventory.models.movement import StockMovement
    from inventory.models.product import Product
    from inventory.services import printer_monitor

    with app.app_context():
        printer_monitor._alerted.clear()
        toner = Product(sku="TN-COST", name="Toner Custo", segment="suprimento", price=180)
        db.session.add(toner)
        db.session.commit()
        m = Machine(kind="impressora", model="PR-COST", ip_address="10.7.7.7",
                    sector="FATURAMENTO", is_active=True, toner_product_id=toner.id)
        db.session.add(m)
        db.session.commit()
        mid, pid = m.id, toner.id

        estado = {"t": 20}
        monkeypatch.setattr("inventory.services.snmp_printer.query",
                            lambda ip, **k: {"ok": True, "pages": 10, "toner_pct": estado["t"], "supplies": []})
        printer_monitor.collect_once(app)     # 20%
        estado["t"] = 100
        printer_monitor.collect_once(app)     # troca -> baixa

        mv = (StockMovement.query.filter_by(product_id=pid, movement_type="OUT").first())
        assert mv is not None
        assert mv.responsible_sector == "FATURAMENTO"
        assert float(mv.unit_cost) == 180.0

        StockMovement.query.filter_by(product_id=pid).delete()
        from inventory.models.printer_reading import PrinterReading
        PrinterReading.query.filter_by(machine_id=mid).delete()
        db.session.delete(db.session.get(Machine, mid))
        db.session.delete(db.session.get(Product, pid))
        db.session.commit()


def test_relatorio_mostra_custo_por_setor(app, auth_client):
    from datetime import datetime
    from inventory.extensions import db
    from inventory.models.movement import StockMovement
    from inventory.models.product import Product
    from inventory.models.category import Category

    with app.app_context():
        # limpa leftovers de execuções anteriores (sku único)
        old = Product.query.filter_by(sku="TN-REP").first()
        if old:
            StockMovement.query.filter_by(product_id=old.id).delete()
            db.session.delete(old)
            db.session.commit()
        # reutiliza uma categoria toner existente ou cria (não apaga categoria)
        cat = Category.query.filter(Category.name.ilike("%toner%")).first()
        if not cat:
            cat = Category(name="Toner PYTEST")
            db.session.add(cat)
            db.session.commit()
        p = Product(sku="TN-REP", name="Toner Rel", category_id=cat.id, price=200)
        db.session.add(p)
        db.session.commit()
        pid = p.id
        for _ in range(2):   # 2 baixas no RH x 200 = 400
            db.session.add(StockMovement(product_id=pid, movement_type="OUT", quantity=1,
                                         unit_cost=200, responsible_sector="RH",
                                         created_at=datetime.now()))
        db.session.commit()

    r = auth_client.get("/machines/impressoras/consumo?dias=7")
    assert r.status_code == 200
    assert "Custo de suprimento por setor".encode() in r.data
    assert b"R$ 400,00" in r.data      # 2 x 200 no RH

    with app.app_context():
        StockMovement.query.filter_by(product_id=pid).delete()
        db.session.delete(db.session.get(Product, pid))
        db.session.commit()
