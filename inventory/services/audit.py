"""
Registro de auditoria (best-effort): nunca quebra o fluxo do app.

Uso:
    from ..services import audit
    audit.record("delete", "ticket", t.id, f"Excluiu chamado {t.code}")
"""
from datetime import timedelta

from flask import request, has_request_context
from flask_login import current_user

from ..extensions import db
from ..models.audit import AuditLog


def record(action: str, entity: str = None, entity_id: int = None, summary: str = None) -> bool:
    """Grava um registro de auditoria. Retorna True se persistiu, False se falhou
    (best-effort: nunca levanta). O retorno permite exigir a trilha antes de
    liberar operações sensíveis, como revelar senhas do Cofre."""
    try:
        uid, uname = None, None
        try:
            if current_user and current_user.is_authenticated:
                uid = current_user.id
                uname = current_user.name
        except Exception:  # noqa: BLE001
            pass
        ip = request.remote_addr if has_request_context() else None
        log = AuditLog(user_id=uid, user_name=uname, action=action,
                       entity=entity, entity_id=entity_id,
                       summary=(summary or "")[:300], ip=ip)
        db.session.add(log)
        db.session.commit()
        return True
    except Exception:  # noqa: BLE001
        # Auditoria jamais derruba a operação principal.
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def build_query(action: str = None, entity: str = None, user: str = None,
                texto: str = None, inicio=None, fim=None):
    """Monta a consulta da trilha, já ordenada do mais recente para o mais antigo.

    Devolve a **query**, não a lista: quem chama pagina no banco. A tela antes
    pedia `list_logs(limit=400)` e paginava a lista em memória, o que impunha um
    teto — nada além dos 400 eventos mais recentes era alcançável, e o rodapé
    ainda anunciava "400 registros" como se fosse o total real. Numa trilha de
    auditoria, que só se consulta depois que algo aconteceu, o histórico antigo
    é justamente o que se procura.

    `fim` é inclusivo: a comparação usa o dia seguinte (`< fim + 1 dia`), senão
    filtrar "até 18/09" perderia tudo o que aconteceu no próprio dia 18.
    """
    q = AuditLog.query
    if action:
        q = q.filter(AuditLog.action == action)
    if entity:
        q = q.filter(AuditLog.entity.ilike(f"%{entity}%"))
    if user:
        q = q.filter(AuditLog.user_name.ilike(f"%{user}%"))
    if texto:
        like = f"%{texto}%"
        q = q.filter(db.or_(AuditLog.summary.ilike(like), AuditLog.ip.ilike(like)))
    if inicio:
        q = q.filter(AuditLog.created_at >= inicio)
    if fim:
        q = q.filter(AuditLog.created_at < fim + timedelta(days=1))
    return q.order_by(AuditLog.id.desc())


def acoes_registradas():
    """Ações distintas presentes na trilha — alimenta o filtro da tela.

    A lista de ações do template era fixa; uma ação nova passava a existir no
    banco sem aparecer no filtro.
    """
    try:
        linhas = db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
        return [a for (a,) in linhas if a]
    except Exception:  # noqa: BLE001 — filtro nunca derruba a página
        return []
