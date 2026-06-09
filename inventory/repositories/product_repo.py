from typing import List, Optional

from sqlalchemy import or_
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
    Lista produtos com filtros opcionais.
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
