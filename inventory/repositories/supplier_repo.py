
from ..extensions import db
from ..models.supplier import Supplier
from ..models.product import Product

def list_suppliers(search=None):
    q = Supplier.query
    if search:
        q = q.filter(Supplier.name.ilike(f"%{search}%"))
    return q.order_by(Supplier.name).all()

def create_supplier(**kwargs):
    s = Supplier(**kwargs); db.session.add(s); db.session.commit(); return s

def update_supplier(s: Supplier, **kwargs):
    for k,v in kwargs.items(): setattr(s,k,v)
    db.session.commit(); return s

def delete_supplier(s: Supplier):
    if Product.query.filter_by(supplier_id=s.id).first():
        raise ValueError("Existem produtos vinculados.")
    db.session.delete(s); db.session.commit()
