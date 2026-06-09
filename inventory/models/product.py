from ..extensions import db

class Product(db.Model):
    # __tablename__ = "product"  # (opcional) deixe comentado se você já tem migrações usando o nome padrão

    id = db.Column(db.Integer, primary_key=True)

    sku = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # NOVOS CAMPOS
    item_type = db.Column(
        db.String(20),
        nullable=False,
        default="product",
        server_default="product",
        index=True,
    )
    unit = db.Column(
        db.String(10),
        nullable=False,
        default="UN",
        server_default="UN",
    )

    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=True)

    min_stock = db.Column(db.Integer, default=0, server_default="0")
    price = db.Column(db.Numeric(12, 2), default=0, server_default="0")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    category = db.relationship("Category", backref=db.backref("products", lazy=True))
    supplier = db.relationship("Supplier", backref=db.backref("products", lazy=True))

    def __repr__(self) -> str:
        return f"<Product id={self.id} sku={self.sku!r} name={self.name!r} type={self.item_type!r} unit={self.unit!r}>"
