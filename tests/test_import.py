"""Import em massa de materiais (CSV) — upsert por SKU + criação de categoria."""
import pytest

from inventory.extensions import db
from inventory.models.product import Product
from inventory.models.category import Category
from inventory.models.machine import Machine
from inventory.services import imports

MARK = "PYTEST"


class _FakeFile:
    def __init__(self, filename, data):
        self.filename = filename
        self._data = data

    def read(self):
        return self._data


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        Product.query.filter(Product.sku.like(f"{MARK}%")).delete()
        Category.query.filter(Category.name.like(f"{MARK}%")).delete()
        Machine.query.filter(Machine.patrimony.like(f"{MARK}%")).delete()
        db.session.commit()


def test_import_upsert_and_category_creation(app):
    with app.app_context():
        csv1 = (f"sku;nome;categoria;preco;estoque_minimo\n"
                f"{MARK}-1;Cabo A;{MARK}Cabos;19,90;5\n").encode("utf-8")
        res = imports.import_products(imports.parse_table(_FakeFile("m.csv", csv1)))
        assert res["created"] == 1 and res["updated"] == 0 and res["categorias"] == 1
        p = Product.query.filter_by(sku=f"{MARK}-1").first()
        assert p and p.name == "Cabo A" and p.min_stock == 5 and abs(float(p.price or 0) - 19.90) < 0.01

        # Reimport do mesmo SKU atualiza (não duplica) e não recria a categoria.
        csv2 = f"sku;nome;preco\n{MARK}-1;Cabo A v2;25\n".encode("utf-8")
        res2 = imports.import_products(imports.parse_table(_FakeFile("m.csv", csv2)))
        assert res2["updated"] == 1 and res2["created"] == 0 and res2["categorias"] == 0
        db.session.expire_all()
        p2 = Product.query.filter_by(sku=f"{MARK}-1").first()
        assert p2.name == "Cabo A v2" and abs(float(p2.price or 0) - 25.0) < 0.01


def test_import_machines_upsert_by_patrimony(app):
    with app.app_context():
        csv1 = (f"tipo;nome;marca;modelo;patrimonio;ip\n"
                f"notebook;NB-01;Dell;Latitude;{MARK}-P1;192.168.0.50\n").encode("utf-8")
        res = imports.import_machines(
            imports.parse_table(_FakeFile("m.csv", csv1), imports.MACHINE_ALIASES))
        assert res["created"] == 1 and res["updated"] == 0
        m = Machine.query.filter_by(patrimony=f"{MARK}-P1").first()
        assert m and m.kind == "notebook" and m.name == "NB-01" and m.ip_address == "192.168.0.50"

        # Mesmo patrimônio -> atualiza (não duplica)
        csv2 = f"tipo;nome;patrimonio\ncomputador;NB-01-renomeado;{MARK}-P1\n".encode("utf-8")
        res2 = imports.import_machines(
            imports.parse_table(_FakeFile("m.csv", csv2), imports.MACHINE_ALIASES))
        assert res2["updated"] == 1 and res2["created"] == 0
        db.session.expire_all()
        m2 = Machine.query.filter_by(patrimony=f"{MARK}-P1").first()
        assert m2.name == "NB-01-renomeado" and m2.kind == "computador"


def test_import_machines_requires_name_or_model(app):
    with app.app_context():
        csv = f"tipo;nome;patrimonio\nnotebook;;{MARK}-P9\n".encode("utf-8")
        res = imports.import_machines(
            imports.parse_table(_FakeFile("m.csv", csv), imports.MACHINE_ALIASES))
        assert res["created"] == 0 and res["errors"]


def test_import_requires_sku(app):
    with app.app_context():
        csv = "sku;nome\n;SemSku\n".encode("utf-8")
        res = imports.import_products(imports.parse_table(_FakeFile("m.csv", csv)))
        assert res["created"] == 0 and any("SKU" in e for e in res["errors"])
