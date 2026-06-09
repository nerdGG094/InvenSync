# inventory/routes/kanban.py
"""
Board Kanban de saúde de estoque.

Agrupa os produtos em colunas conforme o saldo atual versus o estoque mínimo:
  - Sem estoque      (saldo <= 0)
  - Abaixo do mínimo (0 < saldo <= mínimo)
  - Atenção          (mínimo < saldo <= mínimo * 1.5)  -> margem curta
  - Saudável         (saldo > mínimo * 1.5  ou  sem mínimo definido e saldo > 0)
"""
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, case

from ..extensions import db
from ..models.product import Product
from ..models.movement import StockMovement

bp = Blueprint("kanban", __name__)


def _stock_map():
    """Calcula o saldo de todos os produtos em uma única query (Entradas - Saídas)."""
    signed_qty = func.sum(
        case(
            (StockMovement.movement_type == "IN", StockMovement.quantity),
            else_=-StockMovement.quantity,
        )
    )
    rows = (
        db.session.query(StockMovement.product_id, signed_qty)
        .group_by(StockMovement.product_id)
        .all()
    )
    return {pid: int(qty or 0) for pid, qty in rows}


def _classify(stock: int, minimo: int) -> str:
    if stock <= 0:
        return "out"
    if minimo and stock <= minimo:
        return "low"
    if minimo and stock <= minimo * 1.5:
        return "warn"
    return "ok"


@bp.route("")
@login_required
def board():
    products = Product.query.order_by(Product.name.asc()).all()
    stock_by_id = _stock_map()

    columns = {
        "out":  {"key": "out",  "title": "Sem estoque",      "icon": "x-octagon",          "accent": "danger",  "cards": []},
        "low":  {"key": "low",  "title": "Abaixo do mínimo",  "icon": "exclamation-triangle","accent": "warning", "cards": []},
        "warn": {"key": "warn", "title": "Atenção (margem curta)", "icon": "hourglass-split","accent": "info",    "cards": []},
        "ok":   {"key": "ok",   "title": "Saudável",          "icon": "check-circle",        "accent": "success", "cards": []},
    }

    for p in products:
        stock = stock_by_id.get(p.id, 0)
        minimo = int(p.min_stock or 0)
        col = _classify(stock, minimo)
        pct = int(min(stock / minimo * 100, 100)) if minimo > 0 and stock > 0 else (100 if stock > 0 else 0)
        columns[col]["cards"].append({
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "unit": p.unit,
            "category": p.category.name if p.category else None,
            "supplier": p.supplier.name if p.supplier else None,
            "price": float(p.price or 0),
            "stock": stock,
            "minimo": minimo,
            "pct": pct,
        })

    ordered = [columns["out"], columns["low"], columns["warn"], columns["ok"]]
    total = len(products)
    return render_template("kanban.html", columns=ordered, total=total)
