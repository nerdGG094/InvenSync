"""
Registro central de erros — best-effort, NUNCA levanta exceção.

Use `record(source, exc=..., message=...)` de qualquer lugar (rotas, serviços de
fundo, blocos try/except). Captura o traceback e, se houver requisição, o
caminho/método/usuário. Também é ligado ao sinal `got_request_exception` no
create_app para pegar automaticamente as exceções não tratadas das requisições.
"""
import traceback as _tb

from flask import request, has_request_context
from flask_login import current_user

from ..extensions import db


def record(source, exc=None, message=None, level="error"):
    """Grava um erro no banco. Seguro para chamar de qualquer contexto."""
    try:
        from ..models.error_log import ErrorLog
        msg = message or (str(exc) if exc is not None else "")
        tb = None
        if exc is not None:
            tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
        path = method = None
        uid = None
        if has_request_context():
            path = request.path
            method = request.method
            try:
                uid = current_user.id if current_user.is_authenticated else None
            except Exception:  # noqa: BLE001
                uid = None
        e = ErrorLog(level=level, source=(source or "")[:120], message=(msg or "")[:500],
                     traceback=tb, path=path, method=method, user_id=uid)
        db.session.add(e)
        db.session.commit()
    except Exception:  # noqa: BLE001
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass


def recent(limit=300):
    from ..models.error_log import ErrorLog
    return ErrorLog.query.order_by(ErrorLog.created_at.desc()).limit(limit).all()


def count():
    from ..models.error_log import ErrorLog
    return ErrorLog.query.count()


def clear_all():
    from ..models.error_log import ErrorLog
    ErrorLog.query.delete()
    db.session.commit()
