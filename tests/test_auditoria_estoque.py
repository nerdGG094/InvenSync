"""Trilha de auditoria do estoque.

O modulo que da nome ao sistema era o unico sem rastro: movements.py nao
tinha nenhuma chamada a audit.record e products.py so auditava a importacao
em massa -- enquanto tomadas inteligentes e cofre registravam tudo.
"""
import pytest

from inventory.extensions import db
from inventory.models.audit import AuditLog
from inventory.models.movement import StockMovement
from inventory.models.product import Product

MARK = "PYTESTAUD"


@pytest.fixture(autouse=True)
def _limpa(app):
    yield
    with app.app_context():
        # As movimentacoes primeiro: elas tem FK para o produto e o teste de
        # movimentacao cria uma, entao apagar o produto antes viola a restricao.
        ids = [p.id for p in Product.query.filter(Product.sku.like(f"{MARK}%")).all()]
        if ids:
            StockMovement.query.filter(StockMovement.product_id.in_(ids)).delete(
                synchronize_session=False)
            Product.query.filter(Product.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


def _ultimo(app, entity, action):
    with app.app_context():
        return (AuditLog.query.filter_by(entity=entity, action=action)
                .order_by(AuditLog.id.desc()).first())


def test_movimentacao_entra_na_trilha(auth_client, app):
    with app.app_context():
        p = Product(sku=f"{MARK}-MOV", name="Material de teste", unit="UN")
        db.session.add(p)
        db.session.commit()
        pid = p.id

    r = auth_client.post("/movements", data={
        "product_id": pid, "movement_type": "OUT", "quantity": 3,
        "responsible_user": "", "responsible_sector": "Manutencao", "note": "",
    }, follow_redirects=True)
    assert r.status_code == 200

    reg = _ultimo(app, "movement", "create")
    assert reg is not None, "movimentacao nao gerou registro de auditoria"
    assert "Sa" in (reg.summary or "") and "3" in (reg.summary or "")


def test_produto_criado_editado_e_excluido_deixam_rastro(auth_client, app):
    r = auth_client.post("/products/new", data={
        "sku": f"{MARK}-P1", "name": "Item auditado", "unit": "UN",
        "item_type": "product", "min_stock": 1, "category_id": 0, "supplier_id": 0,
    }, follow_redirects=True)
    assert r.status_code == 200

    criado = _ultimo(app, "product", "create")
    assert criado and f"{MARK}-P1" in (criado.summary or "")

    with app.app_context():
        p = Product.query.filter_by(sku=f"{MARK}-P1").first()
        assert p is not None
        pid = p.id

    auth_client.post(f"/products/{pid}/edit", data={
        "sku": f"{MARK}-P1", "name": "Item renomeado", "unit": "UN",
        "item_type": "product", "min_stock": 7, "category_id": 0, "supplier_id": 0,
    }, follow_redirects=True)
    editado = _ultimo(app, "product", "update")
    assert editado, "edicao nao gerou registro"
    # O resumo tem que dizer O QUE mudou, nao so que mudou
    assert "→" in (editado.summary or ""), editado.summary

    auth_client.post(f"/products/{pid}/delete", follow_redirects=True)
    excluido = _ultimo(app, "product", "delete")
    assert excluido and f"{MARK}-P1" in (excluido.summary or ""), \
        "o resumo da exclusao precisa identificar o que foi apagado"
