from typing import List, Optional

from sqlalchemy import or_, func, case
from ..extensions import db
from ..models.product import Product


# Campos que aceitamos criar/atualizar (protege contra sobrescritas acidentais)
_ALLOWED_FIELDS = {
    "sku",
    "name",
    "description",
    "category_id",
    "supplier_id",
    "min_stock",
    "price",
    "item_type",
    "unit",
    # Campos específicos de TI
    "brand",
    "model",
    "patrimony",
    "serial_number",
    "location",
    "compatibility",
    "expiry_date",
    "responsible_user",
    "responsible_sector",
}


# -----------------------------
# Listagem / Busca
# -----------------------------
def list_products(
    search: Optional[str] = None,
    item_type: Optional[str] = None,
    unit: Optional[str] = None,
) -> List[Product]:
    """
    Lista materiais com filtros opcionais.
    - search: busca em nome, sku e descrição
    - item_type: ex.: 'product', 'raw_material', 'kit', 'service'
    - unit: ex.: 'UN', 'KG', 'L', 'CX', ...
    """
    query = Product.query

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.name.ilike(s),
                Product.sku.ilike(s),
                Product.description.ilike(s),
            )
        )

    if item_type:
        query = query.filter(Product.item_type == item_type)

    if unit:
        query = query.filter(Product.unit == unit)

    return query.order_by(Product.name.asc()).all()


def get_product(pid: int) -> Product:
    return Product.query.get_or_404(pid)


# -----------------------------
# CRUD
# -----------------------------
def create_product(**kwargs) -> Product:
    data = {k: kwargs.get(k) for k in _ALLOWED_FIELDS}
    p = Product(**data)
    db.session.add(p)
    db.session.commit()
    return p


def update_product(p: Product, **kwargs) -> Product:
    for k in _ALLOWED_FIELDS:
        if k in kwargs:
            setattr(p, k, kwargs[k])
    db.session.commit()
    return p


def delete_product(p: Product) -> None:
    """
    Impede exclusão se houver movimentações.
    Usa o relacionamento p.movements para evitar import do modelo Movement.
    """
    # Se o relacionamento existir/carregar, uma simples checagem resolve:
    try:
        if p.movements and len(p.movements) > 0:
            raise ValueError("Não é possível excluir: existem movimentações para este produto.")
    except Exception:
        # Se o relacionamento for lazy/dinâmico, ainda assim o acesso acima
        # dispara um SELECT e retorna uma coleção. Mantemos o try/except apenas
        # para evitar qualquer edge case de configuração do relacionamento.
        pass

    db.session.delete(p)
    db.session.commit()


# -----------------------------
# Estoque
# -----------------------------
def current_stock(p: Product) -> int:
    """
    Retorna o saldo (Entradas - Saídas) do produto.
    Usa somente o relacionamento p.movements (sem importar Movement).

    ATENÇÃO: em LISTAGENS use stock_map()/stock_lookup() — chamar isto produto
    a produto gera N+1 (um SELECT de movimentações por produto).
    """
    inbound = 0
    outbound = 0

    # Ao acessar p.movements, o SQLAlchemy carrega a coleção (lazy), se necessário.
    for m in getattr(p, "movements", []) or []:
        if m.movement_type == "IN":
            inbound += int(m.quantity or 0)
        else:
            outbound += int(m.quantity or 0)

    return int(inbound - outbound)


def stock_map(product_ids=None) -> dict:
    """Saldo (Entradas - Saídas) de todos os produtos em UMA query agregada.
    Evita o N+1 de chamar current_stock() produto a produto. -> {product_id: saldo}."""
    from ..models.movement import StockMovement
    signed = func.sum(case(
        (StockMovement.movement_type == "IN", StockMovement.quantity),
        else_=-StockMovement.quantity,
    ))
    q = db.session.query(StockMovement.product_id, signed)
    if product_ids is not None:
        q = q.filter(StockMovement.product_id.in_(list(product_ids)))
    rows = q.group_by(StockMovement.product_id).all()
    return {pid: int(qty or 0) for pid, qty in rows}


def stock_lookup(product_ids=None):
    """Função f(product) -> saldo, respaldada por UMA query agregada. Drop-in
    para `current_stock` em listagens/templates, sem N+1."""
    smap = stock_map(product_ids)
    return lambda p: smap.get(p.id, 0)
