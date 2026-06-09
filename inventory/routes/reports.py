
from flask import Blueprint, render_template, Response
from flask_login import login_required
from io import StringIO
import csv
from ..repositories.product_repo import list_products, current_stock

bp = Blueprint("reports", __name__)

@bp.route("/stock")
@login_required
def stock():
    products = list_products()
    return render_template("reports/stock.html", products=products, current_stock=current_stock)

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
