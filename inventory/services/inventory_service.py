
from ..repositories.product_repo import stock_map
from ..models.product import Product

def low_stock_products(products: list[Product]):
    # Saldo de todos numa única query agregada (evita N+1 de current_stock).
    smap = stock_map()
    return [p for p in products if smap.get(p.id, 0) <= (p.min_stock or 0)]
