from ..extensions import db

class StockMovement(db.Model):
    __tablename__ = "stock_movement"  # <- garante compatibilidade com migrations

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    movement_type = db.Column(db.String(3), nullable=False)  # 'IN' ou 'OUT'
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)

    # Nota fiscal anexada (apenas entradas): nome salvo em disco e nome original
    nf_filename = db.Column(db.String(255), nullable=True)
    nf_original_name = db.Column(db.String(255), nullable=True)

    # Usuário responsável (de Máquinas) + setor — ex.: para quem foi o item
    responsible_user = db.Column(db.String(150), nullable=True, index=True)
    responsible_sector = db.Column(db.String(120), nullable=True)

    # quem fez a movimentação
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    user = db.relationship("User", backref="stock_movements", lazy="joined")

    # produto (sem cascade, para não apagar movimentos ao excluir produto)
    product = db.relationship(
        "Product",
        backref=db.backref("movements", lazy=True)
    )

    def __repr__(self):
        return f"<StockMovement id={self.id} product_id={self.product_id} type={self.movement_type} qty={self.quantity}>"
