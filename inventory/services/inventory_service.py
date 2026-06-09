
from ..repositories.product_repo import current_stock
from ..models.product import Product

def low_stock_products(products: list[Product]):
    return [p for p in products if current_stock(p) <= (p.min_stock or 0)]
