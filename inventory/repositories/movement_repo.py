# inventory/repositories/movement_repo.py
from flask_login import current_user
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
