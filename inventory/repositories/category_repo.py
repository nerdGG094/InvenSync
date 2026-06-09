
from ..extensions import db
from ..models.category import Category
from ..models.product import Product

def list_categories(search=None):
    q = Category.query
    if search:
        q = q.filter(Category.name.ilike(f"%{search}%"))
    return q.order_by(Category.name).all()

def create_category(name, description=None):
    c = Category(name=name, description=description)
    db.session.add(c); db.session.commit(); return c

def update_category(c: Category, name, description=None):
    c.name = name; c.description = description; db.session.commit(); return c

def delete_category(c: Category):
    if Product.query.filter_by(category_id=c.id).first():
        raise ValueError("Existem produtos na categoria.")
    db.session.delete(c); db.session.commit()
