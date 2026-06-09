# inventory/routes/dashboard.py
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from ..repositories.product_repo import list_products, current_stock
from ..services.inventory_service import low_stock_products
from ..extensions import db
from ..models.movement import StockMovement
from ..models.product import Product
from ..models.user import User

bp = Blueprint("dashboard", __name__)

@bp.route("/")
@login_required
def index():
    # ===== Produtos / Estoque geral =====
    products = list_products() or []
    total_items = sum(max(current_stock(p) or 0, 0) for p in products)
    low = low_stock_products(products) or []

    # ===== Métricas para gráficos de Baixo Estoque =====
    def metrics(p):
        estoque = int(current_stock(p) or 0)
        minimo = int(p.min_stock or 0)
        pct = (estoque / minimo * 100.0) if minimo > 0 and estoque > 0 else 0.0
        return {"sku": p.sku, "name": p.name, "estoque": estoque, "minimo": minimo, "pct": pct}

    low_metrics = [metrics(p) for p in low]
    zero_count = sum(1 for m in low_metrics if m["estoque"] <= 0)
    below_count = sum(1 for m in low_metrics if m["estoque"] > 0 and m["estoque"] < m["minimo"])
    top10_criticos = sorted(low_metrics, key=lambda m: m["pct"])[:10]

    chart_data = {
        "labels": [f'{m["sku"]} - {m["name"]}' for m in top10_criticos],
        "estoque": [m["estoque"] for m in top10_criticos],
        "minimo": [m["minimo"] for m in top10_criticos],
        "zeroCount": zero_count,
        "belowCount": below_count,
    }

    # ===== Top 10 Itens mais movimentados (soma de quantidades IN+OUT) =====
    rows_items = (
        db.session.query(
            Product.sku,
            Product.name,
            func.sum(StockMovement.quantity).label("qty"),
        )
        .join(StockMovement, StockMovement.product_id == Product.id)
        .group_by(Product.id)
        .order_by(func.sum(StockMovement.quantity).desc())
        .limit(10)
        .all()
    )
    top_items_data = {
        "labels": [f"{sku} - {name}" for sku, name, _ in rows_items],
        "data": [int(qty or 0) for _, _, qty in rows_items],
    }

    # ===== Top 10 Usuários que mais movimentaram =====
    rows_users = (
        db.session.query(
            User.name,
            func.count(StockMovement.id).label("movs"),
            func.sum(StockMovement.quantity).label("qty"),
        )
        .join(StockMovement, StockMovement.user_id == User.id)
        .group_by(User.id)
        .order_by(func.sum(StockMovement.quantity).desc())
        .limit(10)
        .all()
    )
    top_users_data = {
        "labels": [name or "—" for name, _, _ in rows_users],
        "qty": [int(qty or 0) for _, _, qty in rows_users],
        "movs": [int(movs or 0) for _, movs, _ in rows_users],
    }

    return render_template(
        "dashboard.html",
        low_stock=low,
        total_items=int(total_items),
        total_products=len(products),
        current_stock=current_stock,
        chart_data=chart_data,
        top_items_data=top_items_data,
        top_users_data=top_users_data,
    )
