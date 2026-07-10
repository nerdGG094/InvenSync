"""
Fonte única de "usuários responsáveis" para os formulários do app.

A fonte da verdade é o cadastro central de pessoas (**Colaboradores**, tabela
`user` — com login opcional). Para não perder nada já registrado, também unimos
os nomes que aparecem nos ativos (Máquinas / Celulares) ainda não cadastrados.
Usado para padronizar o combobox de responsável + setor automático em Chamados,
Celulares, Movimentações, Materiais e Máquinas.
"""
import time

from flask import current_app

from ..extensions import db
from ..models.machine import Machine
from ..models.mobile import MobileDevice
from ..models.user import User

# Cache de curta duração do mapa nome->setor. Ele é reconstruído por 3 varreduras
# (Máquinas, Celulares, Pessoas) e era refeito a CADA render de formulário — caro
# em telas com vários selects. TTL curto + invalidação ao mexer em Colaboradores.
# Desligado sob TESTING para os testes sempre verem o estado atual do banco.
_MAP_CACHE = {"data": None, "ts": 0.0}
_MAP_TTL = 60.0  # segundos


def invalidate_people_cache(*_args, **_kwargs):
    """Zera o cache do mapa de pessoas."""
    _MAP_CACHE["data"] = None


# Invalida o cache automaticamente sempre que uma pessoa/ativo muda (ORM),
# cobrindo Colaboradores, Perfil, Máquinas e Celulares sem fiar em cada rota.
from sqlalchemy import event as _event  # noqa: E402
for _model in (User, Machine, MobileDevice):
    for _evt in ("after_insert", "after_update", "after_delete"):
        _event.listen(_model, _evt, invalidate_people_cache)


def users_sector_map() -> dict:
    """{ nome_da_pessoa: setor/departamento }.

    Base: nomes já usados em ativos (compatibilidade, pega o que foi cadastrado
    desde o último boot). Por cima, o cadastro central de pessoas ativas — a
    fonte da verdade, que inclui quem não tem ativo nem login.
    """
    if (_MAP_CACHE["data"] is not None
            and (time.monotonic() - _MAP_CACHE["ts"]) < _MAP_TTL
            and not current_app.config.get("TESTING")):
        return _MAP_CACHE["data"]

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

    _MAP_CACHE["data"] = info
    _MAP_CACHE["ts"] = time.monotonic()
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


def user_id_for(name):
    """id da pessoa no cadastro central a partir do nome (case-insensitive)."""
    nome = (name or "").strip()
    if not nome:
        return None
    u = User.query.filter(db.func.lower(User.name) == nome.lower()).first()
    return u.id if u else None


def department_id_for(name):
    """id do Departamento a partir do nome (case-insensitive) — mantém a FK
    `User.department_id` em dia ao salvar Colaborador/Perfil."""
    nome = (name or "").strip()
    if not nome:
        return None
    from ..models.department import Department
    d = Department.query.filter(db.func.lower(Department.name) == nome.lower()).first()
    return d.id if d else None


def propagate_person_rename(old_name, new_name):
    """Renomeou uma pessoa? Atualiza o nome em TODOS os registros que a
    referenciam por texto (máquinas, celulares, chips, materiais, movimentações,
    chamados). Mantém tudo consistente enquanto as colunas de texto existem.
    Não faz commit — quem chama commita."""
    old = (old_name or "").strip()
    new = (new_name or "").strip()
    if not old or not new or old.lower() == new.lower():
        return
    from ..models.chip import SimChip
    from ..models.product import Product
    from ..models.movement import StockMovement
    from ..models.ticket import Ticket
    low = old.lower()

    def _ci(col):
        return db.func.lower(db.func.btrim(col)) == low

    Machine.query.filter(_ci(Machine.assigned_user)).update(
        {Machine.assigned_user: new}, synchronize_session=False)
    for col in (MobileDevice.assigned_employee, MobileDevice.assigned_employee_2,
                MobileDevice.assigned_employee_3):
        MobileDevice.query.filter(db.func.lower(db.func.btrim(col)) == low).update(
            {col: new}, synchronize_session=False)
    SimChip.query.filter(_ci(SimChip.assigned_employee)).update(
        {SimChip.assigned_employee: new}, synchronize_session=False)
    Product.query.filter(_ci(Product.responsible_user)).update(
        {Product.responsible_user: new}, synchronize_session=False)
    StockMovement.query.filter(_ci(StockMovement.responsible_user)).update(
        {StockMovement.responsible_user: new}, synchronize_session=False)
    Ticket.query.filter(_ci(Ticket.requester)).update(
        {Ticket.requester: new}, synchronize_session=False)


def propagate_sector_rename(old_name, new_name):
    """Renomeou um departamento? Atualiza o setor (texto) em Colaboradores e em
    todos os ativos/registros que guardam o nome do setor. Não faz commit."""
    old = (old_name or "").strip()
    new = (new_name or "").strip()
    if not old or not new or old.lower() == new.lower():
        return
    from ..models.chip import SimChip
    from ..models.product import Product
    from ..models.movement import StockMovement
    from ..models.ticket import Ticket
    from ..models.credential import Credential
    low = old.lower()
    targets = [
        (User, User.sector), (Machine, Machine.sector), (MobileDevice, MobileDevice.sector),
        (SimChip, SimChip.sector), (Product, Product.responsible_sector),
        (StockMovement, StockMovement.responsible_sector), (Ticket, Ticket.sector),
        (Credential, Credential.sector),
    ]
    for model, col in targets:
        model.query.filter(db.func.lower(db.func.btrim(col)) == low).update(
            {col: new}, synchronize_session=False)


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
