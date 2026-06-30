"""
Fonte única de "usuários responsáveis" para os formulários do app.

A fonte da verdade é o cadastro central de pessoas (**Colaboradores**, tabela
`user` — com login opcional). Para não perder nada já registrado, também unimos
os nomes que aparecem nos ativos (Máquinas / Celulares) ainda não cadastrados.
Usado para padronizar o combobox de responsável + setor automático em Chamados,
Celulares, Movimentações, Materiais e Máquinas.
"""
from ..extensions import db
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

    # Compatibilidade: nomes que já estão nos ativos. Só lemos as duas colunas
    # necessárias (nome + setor) em vez de hidratar os objetos inteiros.
    for nome, sector in db.session.query(Machine.assigned_user, Machine.sector):
        u = (nome or "").strip()
        if u and (u not in info or (not info[u] and sector)):
            info[u] = (sector or "").strip()
    for nome, sector in db.session.query(MobileDevice.assigned_employee, MobileDevice.sector):
        u = (nome or "").strip()
        if u and (u not in info or (not info[u] and sector)):
            info[u] = (sector or "").strip()

    # Fonte da verdade: pessoas ativas do cadastro central (setor = sector).
    for nome, sector in db.session.query(User.name, User.sector).filter_by(is_active=True):
        nome = (nome or "").strip()
        if nome:
            info[nome] = (sector or "").strip() or info.get(nome, "")

    return info


def user_names() -> list:
    """Lista ordenada de colaboradores (para datalist/combobox)."""
    return sorted(users_sector_map().keys(), key=lambda s: s.lower())


def user_choices(blank: str = "— Selecione —") -> list:
    """Choices para SelectField: [('', '— Selecione —'), (nome, nome), ...]."""
    return [("", blank)] + [(u, u) for u in user_names()]


def department_choices(current=None) -> list:
    """Choices para SelectField de departamento: ('' em branco) + departamentos
    ativos (cadastro de Departamentos, a fonte da verdade dos setores).

    Inclui o valor atual (`current`) mesmo que esteja inativo ou ainda não
    cadastrado, para não perder o vínculo ao editar registros antigos com setor
    digitado livremente."""
    from ..models.department import Department
    nomes = [d.name for d in Department.query
             .filter(Department.is_active.is_(True))
             .order_by(Department.name).all()]
    atual = (current or "").strip()
    if atual and atual not in nomes:
        nomes.append(atual)
        nomes.sort(key=str.lower)
    return [("", "— Selecione —")] + [(n, n) for n in nomes]


def sector_for(name: str) -> str:
    """Setor/departamento de uma pessoa, a partir do cadastro (User) — fonte da
    verdade. Usado para preencher o setor automaticamente nos formulários quando
    o campo é deixado em branco. Retorna '' se não souber."""
    nome = (name or "").strip()
    if not nome:
        return ""
    # Casa por nome (case-insensitive) no cadastro central de pessoas.
    p = User.query.filter(
        db.func.lower(User.name) == nome.lower()
    ).first()
    if p and (p.sector or "").strip():
        return p.sector.strip()
    # Compatibilidade: nomes que só existem nos ativos.
    return (users_sector_map().get(nome) or "").strip()
