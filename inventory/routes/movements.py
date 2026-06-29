# inventory/routes/movements.py
import os
import time
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    current_app, send_from_directory, abort,
)
from flask_login import login_required
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func, case, select

from ..repositories import movement_repo
from ..forms.catalog import MovementForm
from ..models.product import Product
from ..models.movement import StockMovement  # para filtrar/consultar com joins
from ..services import people


bp = Blueprint("movements", __name__)

NF_ALLOWED_EXT = {"xml", "pdf"}


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


def _save_nf(file_storage):
    """Salva a NF (XML/PDF) em disco e retorna (nome_salvo, nome_original).

    Retorna (None, None) quando não há arquivo ou a extensão não é permitida.
    """
    if not file_storage or not file_storage.filename:
        return None, None
    safe = secure_filename(file_storage.filename)
    ext = (safe.rsplit(".", 1)[-1] if "." in safe else "").lower()
    if ext not in NF_ALLOWED_EXT:
        return None, None
    folder = current_app.config["NF_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    fname = f"nf_{int(time.time() * 1000)}_{safe}"
    file_storage.save(os.path.join(folder, fname))
    return fname, safe


@bp.route("", methods=["GET", "POST"])
@login_required
def list_and_new():
    # ===== Formulário de criação =====
    form = MovementForm()
    products = Product.query.order_by(Product.name).all()
    form.product_id.choices = [(p.id, f"{p.sku} - {p.name}") for p in products]
    form.responsible_user.choices = people.user_choices("— Nenhum —")

    # Mapa para autopreencher o formulário ao escolher o material: custo unitário
    # (preço do cadastro) e responsável/setor já apontados no item.
    products_info = {
        p.id: {
            "price": float(p.price) if p.price is not None else None,
            "responsible_user": (p.responsible_user or "").strip(),
            "responsible_sector": (p.responsible_sector or "").strip(),
        }
        for p in products
    }

    if form.validate_on_submit():
        # Nota fiscal: só faz sentido em entradas e quando o switch está ligado
        nf_filename = nf_original = None
        if form.movement_type.data == "IN" and form.has_nf.data:
            nf_filename, nf_original = _save_nf(form.nf_file.data)

        movement_repo.create_movement(
            product_id=form.product_id.data,
            movement_type=form.movement_type.data,
            quantity=form.quantity.data,
            unit_cost=form.unit_cost.data,
            note=form.note.data,
            responsible_user=(form.responsible_user.data or "").strip() or None,
            responsible_sector=(form.responsible_sector.data or "").strip() or None,
            nf_filename=nf_filename,
            nf_original_name=nf_original,
        )
        if form.movement_type.data == "IN" and form.has_nf.data and not nf_filename:
            flash("Entrada registrada, mas a NF não foi anexada (envie um XML ou PDF).", "warning")
        else:
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
    per_page = 20
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
    # Valor unitário da saída: custo informado na movimentação ou, na falta, o preço do produto
    price_subq = (
        select(Product.price).where(Product.id == StockMovement.product_id).scalar_subquery()
    )
    unit_value = func.coalesce(StockMovement.unit_cost, price_subq, 0)
    out_money_sum = func.coalesce(
        func.sum(
            case(
                (StockMovement.movement_type != "IN", StockMovement.quantity * unit_value),
                else_=0,
            )
        ),
        0,
    )
    in_total, out_total, out_money, mov_count = query.with_entities(
        in_sum, out_sum, out_money_sum, func.count(StockMovement.id)
    ).one()
    totals = {
        "in_total": int(in_total or 0),
        "out_total": int(out_total or 0),
        "out_money": float(out_money or 0),
        "count": int(mov_count or 0),
    }

    return render_template(
        "movements/list.html",
        form=form,
        items=items,
        pagination=pagination,
        totals=totals,
        users_info=people.users_sector_map(),
        products_info=products_info,
    )


@bp.route("/<int:mid>/nf")
@login_required
def nf(mid):
    """Abre/baixa a nota fiscal anexada a uma entrada."""
    m = StockMovement.query.get_or_404(mid)
    if not m.nf_filename:
        abort(404)
    return send_from_directory(
        current_app.config["NF_FOLDER"],
        m.nf_filename,
        as_attachment=False,
        download_name=m.nf_original_name or m.nf_filename,
    )
