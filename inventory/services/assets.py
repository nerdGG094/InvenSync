"""
Visão consolidada de ativos de TI por colaborador.

Reúne Máquinas (assigned_user) e Celulares (assigned_employee) sob o nome da
pessoa responsável, para a tela "Ativos por Colaborador" e o Termo de
Responsabilidade.
"""
from ..extensions import db
from ..models.machine import Machine
from ..models.mobile import MobileDevice

KIND_LABELS = {"computador": "Computador", "notebook": "Notebook", "impressora": "Impressora"}


def _norm(name: str) -> str:
    return (name or "").strip()


def people_with_assets() -> list:
    """Lista de { name, machines, mobiles, total } ordenada por nome."""
    people = {}

    for m in Machine.query.all():
        nome = _norm(m.assigned_user)
        if not nome:
            continue
        people.setdefault(nome, {"name": nome, "machines": [], "mobiles": []})
        people[nome]["machines"].append(m)

    for d in MobileDevice.query.all():
        # Aparelho pode ser compartilhado: aparece para cada funcionário vinculado.
        for nome in (d.employees or [_norm(d.assigned_employee)]):
            nome = _norm(nome)
            if not nome:
                continue
            people.setdefault(nome, {"name": nome, "machines": [], "mobiles": []})
            people[nome]["mobiles"].append(d)

    result = []
    for p in people.values():
        p["total"] = len(p["machines"]) + len(p["mobiles"])
        result.append(p)
    result.sort(key=lambda x: x["name"].lower())
    return result


def assets_for(name: str) -> dict:
    """Ativos de uma pessoa específica (ou estrutura vazia)."""
    nome = _norm(name)
    if not nome:
        return {"name": nome, "machines": [], "mobiles": [], "sector": "", "total": 0}
    low = nome.lower()
    # Filtra direto no banco (case-insensitive), em vez de varrer todas as linhas.
    machines = (Machine.query
                .filter(db.func.lower(db.func.trim(Machine.assigned_user)) == low)
                .all())
    # Aparelho compartilhado: bate em qualquer um dos 3 campos de funcionário.
    mobiles = (MobileDevice.query
               .filter(db.or_(
                   db.func.lower(db.func.trim(MobileDevice.assigned_employee)) == low,
                   db.func.lower(db.func.trim(MobileDevice.assigned_employee_2)) == low,
                   db.func.lower(db.func.trim(MobileDevice.assigned_employee_3)) == low,
               ))
               .all())
    sector = ""
    for m in machines:
        if m.sector:
            sector = m.sector
            break
    if not sector:
        for d in mobiles:
            if d.sector:
                sector = d.sector
                break
    return {"name": nome, "machines": machines, "mobiles": mobiles,
            "sector": sector, "total": len(machines) + len(mobiles)}
