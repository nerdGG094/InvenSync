# inventory/routes/movements.py
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func, case

from ..repositories import movement_repo
from ..forms.catalog import MovementForm
from ..models.product import Product
from ..models.movement import StockMovement  # para filtrar/consultar com joins


bp = Blueprint("movements", __name__)


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


@bp.route("", methods=["GET", "POST"])
@login_required
def list_and_new():
    # ===== Formulário de criação =====
    form = MovementForm()
    form.product_id.choices = [
        (p.id, f"{p.sku} - {p.name}") for p in Product.query.order_by(Product.name).all()
    ]

    if form.validate_on_submit():
        movement_repo.create_movement(
            product_id=form.product_id.data,
            movement_type=form.movement_type.data,
            quantity=form.quantity.data,
            unit_cost=form.unit_cost.data,
            note=form.note.data,
        )
        flash("Movimentação registrada!", "success")
        return redirect(url_for("movements.list_and_new"))

    # ===== Filtros do histórico =====
    q = (request.args.get("q") or "").strip()
    type_filter = (request.args.get("type") or "").strip().upper()
    start_raw = (request.args.get("start") or "").strip()
    end_raw = (request.args.get("end") or "").strip()

    start_dt = _parse_date(start_raw)
    end_dt = _parse_date(end_raw)
    # incluir o dia final completo (<= 23:59:59) usando "< next_day"
    if end_dt:
        end_dt = end_dt + timedelta(days=1)

    # ===== Query com eager load + filtros =====
    query = (
        StockMovement.query
        .options(
            joinedload(StockMovement.product),
            joinedload(StockMovement.user),
        )
    )

    # filtro por texto: produto (nome/sku) ou observação
    if q:
        like = f"%{q}%"
        # join necessário para filtrar por campos do produto
        query = query.join(Product).filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                StockMovement.note.ilike(like),
            )
        )

    # filtro por tipo
    if type_filter in ("IN", "OUT"):
        query = query.filter(StockMovement.movement_type == type_filter)

    # filtro por datas
    if start_dt:
        query = query.filter(StockMovement.created_at >= start_dt)
    if end_dt:
        query = query.filter(StockMovement.created_at < end_dt)

    # ===== Paginação =====
    page = request.args.get("page", 1, type=int)
    per_page = 15
    pagination = (
        query.order_by(StockMovement.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    items = pagination.items

    # ===== Totais dos cards (sobre TODO o filtro, não só a página atual) =====
    in_sum = func.coalesce(
        func.sum(case((StockMovement.movement_type == "IN", StockMovement.quantity), else_=0)), 0
    )
    out_sum = func.coalesce(
        func.sum(case((StockMovement.movement_type != "IN", StockMovement.quantity), else_=0)), 0
    )
    in_total, out_total, mov_count = query.with_entities(
        in_sum, out_sum, func.count(StockMovement.id)
    ).one()
    totals = {
        "in_total": int(in_total or 0),
        "out_total": int(out_total or 0),
        "count": int(mov_count or 0),
    }

    return render_template(
        "movements/list.html",
        form=form,
        items=items,
        pagination=pagination,
        totals=totals,
    )
