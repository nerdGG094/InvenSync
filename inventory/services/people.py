"""
Fonte única de "usuários responsáveis" para os formulários do app.

A fonte da verdade agora é o cadastro central de **Colaboradores**. Para não
perder nada já registrado, também unimos os nomes que já aparecem nos ativos
(Máquinas / Celulares). Usado para padronizar o combobox de responsável + setor
automático em Chamados, Celulares, Movimentações, Produtos e Máquinas.
"""
from ..models.machine import Machine
from ..models.mobile import MobileDevice
from ..models.colaborador import Colaborador


def users_sector_map() -> dict:
    """{ nome_do_colaborador: setor/departamento }.

    Base: nomes já usados em ativos (compatibilidade). Por cima, o cadastro de
    Colaboradores ativos — que é a fonte da verdade e inclui quem não tem ativo
    (ex.: pessoa que só possui celular, ou nenhum equipamento ainda).
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

    # Fonte da verdade: colaboradores ativos (departamento = setor).
    for c in Colaborador.query.filter_by(is_active=True).all():
        nome = (c.name or "").strip()
        if nome:
            info[nome] = (c.department or "").strip() or info.get(nome, "")

    return info


def user_names() -> list:
    """Lista ordenada de colaboradores (para datalist/combobox)."""
    return sorted(users_sector_map().keys(), key=lambda s: s.lower())


def user_choices(blank: str = "— Selecione —") -> list:
    """Choices para SelectField: [('', '— Selecione —'), (nome, nome), ...]."""
    return [("", blank)] + [(u, u) for u in user_names()]
