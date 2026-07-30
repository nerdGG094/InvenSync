"""Regressão: busca no /movements não pode dar 500 (subquery de preço + join Product)."""


def test_busca_movimentos_com_produto_nao_da_500(app, auth_client):
    from inventory.extensions import db
    from inventory.models.product import Product
    from inventory.models.movement import StockMovement
    with app.app_context():
        p = Product(sku="MOVSRCH-1", name="Toner Busca XYZ", price=100)
        db.session.add(p)
        db.session.commit()
        pid = p.id
        db.session.add(StockMovement(product_id=pid, movement_type="OUT", quantity=2))
        db.session.add(StockMovement(product_id=pid, movement_type="IN", quantity=5))
        db.session.commit()

    # a busca faz join(Product) — o bug era "no FROM clauses" no subquery de preço
    r = auth_client.get("/movements?q=Busca+XYZ")
    assert r.status_code == 200
    assert b"Toner Busca XYZ" in r.data

    with app.app_context():
        StockMovement.query.filter_by(product_id=pid).delete()
        db.session.delete(db.session.get(Product, pid))
        db.session.commit()
