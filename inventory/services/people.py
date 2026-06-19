"""
Fonte única de "usuários responsáveis" para os formulários do app.

A fonte da verdade é o cadastro central de pessoas (**Colaboradores**, tabela
`user` — com login opcional). Para não perder nada já registrado, também unimos
os nomes que aparecem nos ativos (Máquinas / Celulares) ainda não cadastrados.
Usado para padronizar o combobox de responsável + setor automático em Chamados,
Celulares, Movimentações, Materiais e Máquinas.
"""
from ..models.machine import Machine
from ..models.mobile import MobileDevice
from ..models.user import User


def users_sector_map() -> dict:
    """{ nome_da_pessoa: setor/departamento }.

    Base: nomes já usados em ativos (compatibilidade, pega o que foi cadastrado
    desde o último boot). Por cima, o cadastro central de pessoas ativas — a
    fonte da verdade, que inclui quem não tem ativo nem login.
    """
    info = {}

    # Compatibilidade: nomes que já estão nos ativos.
    for m in Machine.query.all():
        u = (m.assigned_user or "").strip()
        if u and (u not in info or (not info[u] and m.sector)):
            info[u] = (m.sector or "").strip()
    for d in MobileDevice.query.all():
        u = (d.assigned_employee or "").strip()
        if u and (u not in info or (not info[u] and d.sector)):
            info[u] = (d.sector or "").strip()

    # Fonte da verdade: pessoas ativas do cadastro central (setor = sector).
    for p in User.query.filter_by(is_active=True).all():
        nome = (p.name or "").strip()
        if nome:
            info[nome] = (p.sector or "").strip() or info.get(nome, "")

    return info


def user_names() -> list:
    """Lista ordenada de colaboradores (para datalist/combobox)."""
    return sorted(users_sector_map().keys(), key=lambda s: s.lower())


def user_choices(blank: str = "— Selecione —") -> list:
    """Choices para SelectField: [('', '— Selecione —'), (nome, nome), ...]."""
    return [("", blank)] + [(u, u) for u in user_names()]
