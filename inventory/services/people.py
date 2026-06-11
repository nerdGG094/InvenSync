"""
Fonte única de "usuários responsáveis" para os formulários do app.

Os usuários e seus setores vêm do cadastro de Máquinas (campo assigned_user /
sector). Usado para padronizar o combobox de responsável + setor automático
em Chamados, Celulares, Movimentações, Produtos e Máquinas.
"""
from ..models.machine import Machine


def users_sector_map() -> dict:
    """{ nome_do_usuario: setor } a partir das máquinas cadastradas."""
    info = {}
    for m in Machine.query.all():
        u = (m.assigned_user or "").strip()
        if u and (u not in info or (not info[u] and m.sector)):
            info[u] = (m.sector or "").strip()
    return info


def user_names() -> list:
    """Lista ordenada de usuários cadastrados (para datalist/combobox)."""
    return sorted(users_sector_map().keys(), key=lambda s: s.lower())


def user_choices(blank: str = "— Selecione —") -> list:
    """Choices para SelectField: [('', '— Selecione —'), (nome, nome), ...]."""
    return [("", blank)] + [(u, u) for u in user_names()]
