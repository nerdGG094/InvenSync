from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from ..repositories import product_repo
from ..forms.catalog import ProductForm
from ..models.product import Product
from ..models.category import Category
from ..models.supplier import Supplier

bp = Blueprint("products", __name__)

# ===== CHOICES padronizados =====
TYPE_CHOICES = [
    ("product", "Produto"),
    ("raw_material", "Insumo"),
    ("kit", "Kit/Combo"),
    ("service", "Serviço"),
]

UNIT_CHOICES = [
    ("UN",  "Unidade"),
    ("PC",  "Peça"),
    ("CX",  "Caixa"),
    ("DZ",  "Dúzia"),
    ("PCT", "Pacote"),
    ("JG",  "Jogo"),
    ("PAR", "Par"),
    ("RL",  "Rolo"),
    ("KG",  "Quilo (kg)"),
    ("G",   "Grama (g)"),
    ("MG",  "Miligramas (mg)"),
    ("L",   "Litro (L)"),
    ("ML",  "Mililitro (mL)"),
    ("M",   "Metro (m)"),
    ("CM",  "Centímetro (cm)"),
    ("MM",  "Milímetro (mm)"),
    ("M2",  "Metro quadrado (m²)"),
    ("M3",  "Metro cúbico (m³)"),
    ("KIT", "Kit/Conjunto"),
    ("HR",  "Hora"),
    ("MIN", "Minuto"),
]

def _populate_choices(form: ProductForm) -> None:
    form.category_id.choices = [(0, "-- Nenhuma --")] + [
        (c.id, c.name) for c in Category.query.order_by(Category.name).all()
    ]
    form.supplier_id.choices = [(0, "-- Nenhum --")] + [
        (s.id, s.name) for s in Supplier.query.order_by(Supplier.name).all()
    ]
    form.item_type.choices = TYPE_CHOICES
    form.unit.choices = UNIT_CHOICES

def _form_to_kwargs(form: ProductForm) -> dict:
    return dict(
        sku=(form.sku.data or "").strip(),
        name=(form.name.data or "").strip(),
        description=form.description.data,
        category_id=None if form.category_id.data == 0 else form.category_id.data,
        supplier_id=None if form.supplier_id.data == 0 else form.supplier_id.data,
        min_stock=form.min_stock.data or 0,
        price=form.price.data or 0,
        item_type=form.item_type.data or "product",
        unit=form.unit.data or "UN",
        # Campos específicos de TI
        brand=(form.brand.data or "").strip() or None,
        model=(form.model.data or "").strip() or None,
        patrimony=(form.patrimony.data or "").strip() or None,
        serial_number=(form.serial_number.data or "").strip() or None,
        location=(form.location.data or "").strip() or None,
        compatibility=(form.compatibility.data or "").strip() or None,
        expiry_date=form.expiry_date.data or None,
    )

@bp.route("")
@login_required
def list_view():
    q = request.args.get("q", "")
    items = product_repo.list_products(q)
    return render_template(
        "products/list.html",
        items=items,
        q=q,
        current_stock=product_repo.current_stock,
    )

@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = ProductForm()
    _populate_choices(form)

    # defaults no GET
    if request.method == "GET":
        if not form.item_type.data:
            form.item_type.data = "product"
        if not form.unit.data:
            form.unit.data = "UN"

    if form.validate_on_submit():
        try:
            product_repo.create_product(**_form_to_kwargs(form))
            flash("Produto criado!", "success")
            return redirect(url_for("products.list_view"))
        except IntegrityError:
            flash("Erro: SKU deve ser único.", "danger")
        except Exception:
            flash("Erro ao criar produto.", "danger")

    return render_template("products/form.html", form=form, title="Novo Produto")

@bp.route("/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def edit(pid):
    p = Product.query.get_or_404(pid)

    # Para garantir que as choices existam ANTES de processar os dados do objeto:
    form = ProductForm()
    _populate_choices(form)

    if request.method == "GET":
        # preenche o formulário com o objeto
        form.process(obj=p)
        # mantém seleção nula como 0 nos selects dinâmicos
        form.category_id.data = p.category_id or 0
        form.supplier_id.data = p.supplier_id or 0

    if form.validate_on_submit():
        try:
            product_repo.update_product(p, **_form_to_kwargs(form))
            flash("Produto atualizado!", "success")
            return redirect(url_for("products.list_view"))
        except IntegrityError:
            flash("Erro: SKU deve ser único.", "danger")
        except Exception:
            flash("Erro ao atualizar produto.", "danger")

    return render_template("products/form.html", form=form, title="Editar Produto")

@bp.route("/<int:pid>/delete", methods=["POST"])
@login_required
def delete(pid):
    p = Product.query.get_or_404(pid)
    try:
        product_repo.delete_product(p)
        flash("Produto excluído.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    except Exception:
        flash("Erro ao excluir produto.", "danger")
    return redirect(url_for("products.list_view"))
