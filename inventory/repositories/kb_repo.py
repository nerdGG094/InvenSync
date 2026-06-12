from typing import List, Optional

from sqlalchemy import or_

from ..extensions import db
from ..models.kb import KbArticle

_ALLOWED = {"title", "category", "problem", "solution", "tags"}


def list_articles(search: Optional[str] = None, category: Optional[str] = None) -> List[KbArticle]:
    query = KbArticle.query
    if category:
        query = query.filter(KbArticle.category == category)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(
            KbArticle.title.ilike(s),
            KbArticle.problem.ilike(s),
            KbArticle.solution.ilike(s),
            KbArticle.tags.ilike(s),
        ))
    return query.order_by(KbArticle.views.desc(), KbArticle.title.asc()).all()


def get_article(aid: int) -> KbArticle:
    return KbArticle.query.get_or_404(aid)


def create_article(created_by_id=None, **kwargs) -> KbArticle:
    a = KbArticle(created_by_id=created_by_id, **{k: kwargs.get(k) for k in _ALLOWED})
    db.session.add(a)
    db.session.commit()
    return a


def update_article(a: KbArticle, **kwargs) -> KbArticle:
    for k in _ALLOWED:
        if k in kwargs:
            setattr(a, k, kwargs[k])
    db.session.commit()
    return a


def delete_article(a: KbArticle) -> None:
    db.session.delete(a)
    db.session.commit()


def increment_views(a: KbArticle) -> None:
    a.views = (a.views or 0) + 1
    db.session.commit()
