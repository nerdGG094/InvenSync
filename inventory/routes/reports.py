
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, Response
from flask_login import login_required
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from io import StringIO
import csv
from ..repositories.product_repo import list_products, current_stock
from ..models.product import Product
from ..models.movement import StockMovement

bp = Blueprint("reports", __name__)


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


def _saidas_query():
    """Movimentações de saída (OUT) filtradas por data/texto, mais recentes primeiro."""
    q = (request.args.get("q") or "").strip()
    start_dt = _parse_date((request.args.get("start") or "").strip())
    end_dt = _parse_date((request.args.get("end") or "").strip())
    if end_dt:
        end_dt = end_dt + timedelta(days=1)  # inclui o dia final completo

    query = (
        StockMovement.query
        .options(joinedload(StockMovement.product), joinedload(StockMovement.user))
        .filter(StockMovement.movement_type != "IN")
    )
    if q:
        like = f"%{q}%"
        query = query.join(Product).filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                StockMovement.note.ilike(like),
            )
        )
    if start_dt:
        query = query.filter(StockMovement.created_at >= start_dt)
    if end_dt:
        query = query.filter(StockMovement.created_at < end_dt)

    return query.order_by(StockMovement.created_at.desc())


def _saida_unit_value(m):
    """Custo unitário informado na saída ou, na falta, o preço cadastrado do produto."""
    if m.unit_cost is not None:
        return float(m.unit_cost)
    if m.product and m.product.price is not None:
        return float(m.product.price)
    return 0.0

@bp.route("/stock")
@login_required
def stock():
    products = list_products()
    return render_template("reports/stock.html", products=products, current_stock=current_stock)

@bp.route("/saidas")
@login_required
def saidas():
    movements = _saidas_query().all()
    rows = []
    total_qty = 0
    total_value = 0.0
    for m in movements:
        unit_value = _saida_unit_value(m)
        line_total = unit_value * (m.quantity or 0)
        total_qty += (m.quantity or 0)
        total_value += line_total
        rows.append({"m": m, "unit_value": unit_value, "line_total": line_total})
    return render_template(
        "reports/saidas.html",
        rows=rows,
        total_qty=total_qty,
        total_value=total_value,
        count=len(rows),
    )


@bp.route("/export/saidas.csv")
@login_required
def export_saidas():
    si = StringIO()
    cw = csv.writer(si, delimiter=";")
    cw.writerow([
        "Data", "SKU", "Material", "Quantidade",
        "Valor Unitario", "Valor Total", "Responsavel", "Setor", "Observacao",
    ])
    for m in _saidas_query().all():
        unit_value = _saida_unit_value(m)
        cw.writerow([
            m.created_at.strftime("%d/%m/%Y %H:%M") if m.created_at else "",
            (m.product.sku if m.product else ""),
            (m.product.name if m.product else ""),
            m.quantity or 0,
            f"{unit_value:.2f}".replace(".", ","),
            f"{unit_value * (m.quantity or 0):.2f}".replace(".", ","),
            m.responsible_user or "",
            m.responsible_sector or "",
            (m.note or "").replace("\n", " ").strip(),
        ])
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=saidas.csv"},
    )


@bp.route("/export/products.csv")
@login_required
def export_products():
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow([
        "SKU", "Nome", "Marca", "Modelo", "Categoria", "Fornecedor",
        "Localização", "Nº Patrimônio", "Nº Série", "Compatibilidade",
        "Validade", "Estoque Atual", "Mínimo", "Preço", "Criado em",
    ])
    for p in list_products():
        cw.writerow([
            p.sku, p.name,
            p.brand or "", p.model or "",
            (p.category.name if p.category else ""),
            (p.supplier.name if p.supplier else ""),
            p.location or "", p.patrimony or "", p.serial_number or "",
            (p.compatibility or "").replace("\n", " ").strip(),
            p.expiry_date.strftime("%Y-%m-%d") if p.expiry_date else "",
            current_stock(p),
            p.min_stock or 0,
            f"{p.price:.2f}",
            p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "",
        ])
    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=products.csv"})
