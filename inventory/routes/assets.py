# inventory/routes/assets.py
from datetime import datetime

from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user

from ..services import assets, audit
from ..services.exports import xlsx_response

_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]

KIND_LBL = {"computador": "Computador", "notebook": "Notebook", "impressora": "Impressora"}

bp = Blueprint("assets", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _person_sector(p) -> str:
    """Setor de uma pessoa, deduzido dos próprios ativos (máquina/celular)."""
    for m in p["machines"]:
        if m.sector:
            return m.sector.strip()
    for d in p["mobiles"]:
        if d.sector:
            return d.sector.strip()
    return ""


def _group_by_sector(people: list) -> list:
    """Agrupa pessoas por setor. Retorna [{name, items, maquinas, celulares}],
    setores em ordem alfabética e 'Sem setor' por último."""
    grupos = {}
    for p in people:
        setor = _person_sector(p)
        grupos.setdefault(setor, []).append(p)
    nomeados = sorted((s for s in grupos if s), key=lambda s: s.lower())
    ordem = nomeados + ([""] if "" in grupos else [])
    out = []
    for s in ordem:
        itens = grupos[s]
        # Conta dispositivos ÚNICOS por id: um celular compartilhado por várias
        # pessoas é 1 aparelho, não vários.
        maquinas = {m.id for p in itens for m in p["machines"]}
        celulares = {d.id for p in itens for d in p["mobiles"]}
        out.append({
            "name": s or None,
            "items": itens,
            "maquinas": len(maquinas),
            "celulares": len(celulares),
        })
    return out


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip().lower()
    people = assets.people_with_assets()
    if q:
        people = [p for p in people if q in p["name"].lower()]
    totals = {
        "pessoas": len(people),
        # Dispositivos únicos por id (aparelho compartilhado conta 1).
        "maquinas": len({m.id for p in people for m in p["machines"]}),
        "celulares": len({d.id for p in people for d in p["mobiles"]}),
    }
    grupos = _group_by_sector(people)
    return render_template("assets/list.html", people=people, grupos=grupos,
                           totals=totals, q=request.args.get("q") or "")


@bp.route("/export")
def export():
    people = assets.people_with_assets()
    headers = ["Colaborador", "Setor", "Tipo de ativo", "Equipamento", "Identificador", "Patrimônio"]
    rows = []
    for p in people:
        sector = ""
        for m in p["machines"]:
            if m.sector:
                sector = m.sector
                break
        for m in p["machines"]:
            rows.append([p["name"], m.sector or sector, KIND_LBL.get(m.kind, m.kind),
                         f"{m.brand or ''} {m.model or ''}".strip(),
                         m.ip_address or m.serial_number or "", m.patrimony or ""])
        for d in p["mobiles"]:
            rows.append([p["name"], d.sector or sector, "Celular",
                         f"{d.brand or ''} {d.model or ''}".strip(),
                         d.phone_number or d.imei or "", d.patrimony or ""])
    audit.record("export", "assets", None, f"Exportou ativos de {len(people)} colaborador(es)")
    return xlsx_response("Ativos", headers, rows, filename="ativos_por_colaborador")


@bp.route("/<path:name>")
def detail(name):
    data = assets.assets_for(name)
    if data["total"] == 0:
        abort(404)
    return render_template("assets/detail.html", a=data)


@bp.route("/<path:name>/termo")
def termo(name):
    data = assets.assets_for(name)
    if data["total"] == 0:
        abort(404)
    now = datetime.now()
    data_extenso = f"{now.day} de {_MESES[now.month - 1]} de {now.year}"
    return render_template("assets/termo.html", a=data, data_extenso=data_extenso)
