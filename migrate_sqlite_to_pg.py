"""
Migração única: SQLite (instance/inventory.db) -> PostgreSQL (inventario_almox).

- Cria as tabelas no PostgreSQL a partir dos modelos do app (sem rodar o seed).
- Copia todos os registros preservando os IDs.
- Ajusta as sequences (auto-incremento) para o próximo ID livre.

Uso:  python migrate_sqlite_to_pg.py
"""
import os
import sqlite3
from datetime import datetime

from sqlalchemy import Boolean, DateTime, create_engine, text

from inventory.config import Config
from inventory.extensions import db

# Importa os modelos para registrar o metadata
from inventory.models.user import User              # noqa: F401
from inventory.models.category import Category       # noqa: F401
from inventory.models.supplier import Supplier       # noqa: F401
from inventory.models.product import Product         # noqa: F401
from inventory.models.movement import StockMovement  # noqa: F401

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "instance", "inventory.db")

# Ordem de inserção respeitando as foreign keys
TABLES_IN_ORDER = ["user", "category", "supplier", "product", "stock_movement"]
# Sequences correspondentes (PostgreSQL nomeia <tabela>_<coluna>_seq)
SEQUENCES = {
    "user": "user_id_seq",
    "category": "category_id_seq",
    "supplier": "supplier_id_seq",
    "product": "product_id_seq",
    "stock_movement": "stock_movement_id_seq",
}


def _coerce_row(table_name, row):
    """Converte valores do SQLite para os tipos esperados pelo PostgreSQL."""
    table = db.metadata.tables[table_name]
    out = {}
    for col_name, value in dict(row).items():
        col = table.columns.get(col_name)
        if value is not None and col is not None:
            if isinstance(col.type, Boolean):
                value = bool(value)
            elif isinstance(col.type, DateTime) and isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value)
                except ValueError:
                    value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        out[col_name] = value
    return out


def main():
    pg_engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)

    # 1) Cria todas as tabelas no PostgreSQL
    db.metadata.create_all(pg_engine)
    print("Tabelas criadas/garantidas no PostgreSQL.")

    # 2) Lê dados do SQLite
    sconn = sqlite3.connect(SQLITE_PATH)
    sconn.row_factory = sqlite3.Row
    scur = sconn.cursor()

    with pg_engine.begin() as pg:
        for table in TABLES_IN_ORDER:
            rows = scur.execute(f'SELECT * FROM "{table}"').fetchall()
            if not rows:
                print(f"  {table}: 0 registros (nada a copiar)")
                continue

            cols = rows[0].keys()
            col_list = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join(f":{c}" for c in cols)
            insert_sql = text(
                f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
                f"ON CONFLICT DO NOTHING"
            )
            data = [_coerce_row(table, r) for r in rows]
            pg.execute(insert_sql, data)
            print(f"  {table}: {len(data)} registros copiados")

        # 3) Ajusta as sequences
        for table, seq in SEQUENCES.items():
            pg.execute(
                text(
                    f"SELECT setval('{seq}', "
                    f'COALESCE((SELECT MAX(id) FROM "{table}"), 0) + 1, false)'
                )
            )
        print("Sequences ajustadas.")

    sconn.close()
    print("\nMigração concluída com sucesso.")


if __name__ == "__main__":
    main()
