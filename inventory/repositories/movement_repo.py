# inventory/repositories/movement_repo.py
from flask_login import current_user
from sqlalchemy.orm import joinedload
from ..extensions import db
from ..models.movement import StockMovement

def create_movement(**kwargs):
    # injeta o usuário atual automaticamente
    if getattr(current_user, "is_authenticated", False):
        kwargs.setdefault("user_id", current_user.id)

    m = StockMovement(**kwargs)
    db.session.add(m)
    db.session.commit()
    return m

def list_movements(page=1, per_page=15):
    return (
        StockMovement.query
        .options(
            joinedload(StockMovement.product),  # evita N+1 no produto
            joinedload(StockMovement.user),     # evita N+1 no usuário
        )
        .order_by(StockMovement.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
