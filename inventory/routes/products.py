import re
import unicodedata

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..repositories import product_repo
from ..forms.catalog import ProductForm
from ..models.product import Product
from ..models.category import Category
from ..models.supplier import Supplier
from ..services import people

bp = Blueprint("products", __name__)

# Prefixo de SKU por tipo de item (usado quando não há categoria escolhida)
TYPE_PREFIX = {"product": "PRD", "raw_material": "INS", "kit": "KIT", "service": "SRV"}


def _slug_prefix(text: str, fallback: str = "ITM") -> str:
    """3 letras maiúsculas, sem acento, a partir de um texto."""
    if not text:
        return fallback
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]", "", t).upper()
    return t[:3] or fallback


def _sku_prefix(category_id, item_type) -> str:
    """Prefixo do SKU: pela categoria (melhor p/ TI) ou, na falta, pelo tipo."""
    if category_id:
        c = Category.query.get(int(category_id))
        if c:
            return _slug_prefix(c.name)
    return TYPE_PREFIX.get(item_type or "product", "ITM")


def _next_sku(prefix: str) -> str:
    """Próximo SKU livre no formato PREFIXO-0001 para o prefixo informado."""
    rows = (
        Product.query.filter(Product.sku.like(f"{prefix}-%"))
        .with_entities(Product.sku)
        .all()
    )
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    mx = 0
    for (sku,) in rows:
        m = pat.match(sku or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{prefix}-{mx + 1:04d}"


@bp.route("/suggest-sku")
@login_required
def suggest_sku():
    """Sugere o próximo SKO para (categoria/tipo) — consumido via JS no form."""
    item_type = request.args.get("item_type") or "product"
    category_id = request.args.get("category_id", type=int) or None
    prefix = _sku_prefix(category_id, item_type)
    return jsonify(sku=_next_sku(prefix), prefix=prefix)

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

# Categorias consideradas "suprimentos de impressão" (Toner & Cilindros)
SUPPLY_CATEGORY_NAMES = ("Toner", "Cilindro/Fotocondutor")


def _seg_ctx(segment: str) -> dict:
    """Contexto de visão (título, ícone, URLs) por segmento."""
    if segment == "suprimento":
        return {
            "segment": "suprimento",
            "title": "Toner & Cilindros",
            "icon": "bi-printer",
            "new_label": "Novo Toner/Cilindro",
            "list_url": url_for("products.supplies"),
            "new_url": url_for("products.new", segment="suprimento"),
        }
    return {
        "segment": "equipamento",
        "title": "Produtos",
        "icon": "bi-grid",
        "new_label": "Novo Produto",
        "list_url": url_for("products.list_view"),
        "new_url": url_for("products.new"),
    }


def _populate_choices(form: ProductForm, segment: str = "equipamento") -> None:
    cats = Category.query.order_by(Category.name).all()
    if segment == "suprimento":
        cats = [c for c in cats if c.name in SUPPLY_CATEGORY_NAMES]
    form.category_id.choices = [(0, "-- Nenhuma --")] + [(c.id, c.name) for c in cats]
    form.supplier_id.choices = [(0, "-- Nenhum --")] + [
        (s.id, s.name) for s in Supplier.query.order_by(Supplier.name).all()
    ]
    form.item_type.choices = TYPE_CHOICES
    form.unit.choices = UNIT_CHOICES
    form.responsible_user.choices = people.user_choices("— Nenhum —")

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
        responsible_user=(form.responsible_user.data or "").strip() or None,
        responsible_sector=(form.responsible_sector.data or "").strip() or None,
    )

@bp.route("")
@login_required
def list_view():
    q = request.args.get("q", "")
    items = product_repo.list_products(q, segment="equipamento")
    return render_template(
        "products/list.html",
        items=items, q=q,
        current_stock=product_repo.current_stock,
        seg=_seg_ctx("equipamento"),
    )


@bp.route("/supplies")
@login_required
def supplies():
    """Submódulo Toner & Cilindros (segmento 'suprimento')."""
    q = request.args.get("q", "")
    items = product_repo.list_products(q, segment="suprimento")
    return render_template(
        "products/list.html",
        items=items, q=q,
        current_stock=product_repo.current_stock,
        seg=_seg_ctx("suprimento"),
    )

@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    segment = request.args.get("segment") or "equipamento"
    if segment not in ("equipamento", "suprimento"):
        segment = "equipamento"
    seg = _seg_ctx(segment)

    form = ProductForm()
    _populate_choices(form, segment)

    # defaults no GET
    if request.method == "GET":
        if not form.item_type.data:
            form.item_type.data = "product"
        if not form.unit.data:
            form.unit.data = "UN"

    if form.validate_on_submit():
        # SKU automático: se vier vazio, gera a partir da categoria/tipo.
        auto_sku = not (form.sku.data or "").strip()
        for attempt in range(6):
            if auto_sku:
                form.sku.data = _next_sku(
                    _sku_prefix(form.category_id.data or None, form.item_type.data)
                )
            try:
                kwargs = _form_to_kwargs(form)
                kwargs["segment"] = segment
                product_repo.create_product(**kwargs)
                label = "Toner/Cilindro" if segment == "suprimento" else "Produto"
                flash(f"{label} criado! SKU: {form.sku.data}", "success")
                return redirect(seg["list_url"])
            except IntegrityError:
                db.session.rollback()
                if auto_sku and attempt < 5:
                    continue  # colisão de corrida: tenta o próximo número
                flash("Erro: SKU deve ser único.", "danger")
                break
            except Exception:
                db.session.rollback()
                flash("Erro ao criar item.", "danger")
                break

    title = "Novo Toner/Cilindro" if segment == "suprimento" else "Novo Produto"
    return render_template("products/form.html", form=form, title=title,
                           back_url=seg["list_url"], seg=seg,
                           users_info=people.users_sector_map())

@bp.route("/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def edit(pid):
    p = Product.query.get_or_404(pid)
    segment = p.segment or "equipamento"
    seg = _seg_ctx(segment)

    # Para garantir que as choices existam ANTES de processar os dados do objeto:
    form = ProductForm()
    _populate_choices(form, segment)

    # Garante que o responsável atual apareça no combobox
    if p.responsible_user and p.responsible_user not in [c[0] for c in form.responsible_user.choices]:
        form.responsible_user.choices.append((p.responsible_user, p.responsible_user))

    if request.method == "GET":
        # preenche o formulário com o objeto
        form.process(obj=p)
        # mantém seleção nula como 0 nos selects dinâmicos
        form.category_id.data = p.category_id or 0
        form.supplier_id.data = p.supplier_id or 0

    if form.validate_on_submit():
        try:
            kwargs = _form_to_kwargs(form)
            kwargs["segment"] = segment  # preserva o segmento
            product_repo.update_product(p, **kwargs)
            flash("Item atualizado!", "success")
            return redirect(seg["list_url"])
        except IntegrityError:
            flash("Erro: SKU deve ser único.", "danger")
        except Exception:
            flash("Erro ao atualizar item.", "danger")

    title = "Editar Toner/Cilindro" if segment == "suprimento" else "Editar Produto"
    return render_template("products/form.html", form=form, title=title,
                           back_url=seg["list_url"], seg=seg,
                           users_info=people.users_sector_map())

@bp.route("/<int:pid>/delete", methods=["POST"])
@login_required
def delete(pid):
    p = Product.query.get_or_404(pid)
    seg = _seg_ctx(p.segment or "equipamento")
    try:
        product_repo.delete_product(p)
        flash("Item excluído.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    except Exception:
        flash("Erro ao excluir item.", "danger")
    return redirect(seg["list_url"])
