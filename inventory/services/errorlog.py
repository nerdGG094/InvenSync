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

# Sentinela: distingue "chamador não informou usuário" (aí buscamos em
# current_user) de "chamador informou None" (usuário desconhecido, e NÃO
# devemos tocar em current_user).
_SEM_USUARIO = object()


def record(source, exc=None, message=None, level="error", user_id=_SEM_USUARIO):
    """Grava um erro no banco. Seguro para chamar de qualquer contexto.

    `user_id`: quando o chamador informa (mesmo que None), NÃO tocamos em
    `current_user`. Isso é obrigatório para quem chama de DENTRO do
    `user_loader` do Flask-Login: ler `current_user` ali re-invoca o próprio
    loader (o usuário ainda não está em `g`), e com o `_user_id` presente na
    sessão isso vira recursão infinita — uma requisição falha e derruba o app.
    """
    try:
        from ..models.error_log import ErrorLog
        msg = message or (str(exc) if exc is not None else "")
        tb = None
        if exc is not None:
            tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
        path = method = None
        if user_id is not _SEM_USUARIO:
            uid = user_id                      # fornecido: nunca toca current_user
        else:
            uid = None
        if has_request_context():
            path = request.path
            method = request.method
            if user_id is _SEM_USUARIO:
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
