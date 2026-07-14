# inventory/routes/assets.py
import json
from datetime import datetime

from flask import Blueprint, render_template, request, abort, jsonify
from flask_login import login_required, current_user

from ..extensions import db
from ..models.asset_signature import AssetSignature
from ..models.asset_termo import AssetTermo
from ..services import assets, audit
from ..services.exports import xlsx_response

# Chave reservada para a assinatura (única) do Responsável de TI — reutilizada
# em todos os termos, já que quem entrega os equipamentos é sempre a TI.
TI_KEY = "__ti_responsavel__"


def _sig_key(name: str) -> str:
    return (name or "").strip().lower()


def _valid_signature(data_url: str) -> bool:
    """Assinatura tem que ser exatamente o PNG que o canvas gera (barra SVG e
    outros subtipos), e caber no limite."""
    return (data_url.startswith("data:image/png;base64,")
            and len(data_url) <= 2_000_000)


def _termo_itens(data: dict) -> list:
    """Congela os equipamentos de uma pessoa numa lista simples (p/ o comprovante)."""
    itens = []
    for m in data["machines"]:
        itens.append({
            "tipo": KIND_LBL.get(m.kind, m.kind),
            "equip": f"{m.brand or ''} {m.model or ''}".strip() or "—",
            "pat": m.patrimony or "", "ident": m.ip_address or m.serial_number or "",
        })
    for d in data["mobiles"]:
        itens.append({
            "tipo": "Celular",
            "equip": f"{d.brand or ''} {d.model or ''}".strip() or "—",
            "pat": d.patrimony or "", "ident": d.phone_number or d.imei or "",
        })
    return itens

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
    sig = AssetSignature.query.filter_by(person_key=_sig_key(name)).first()
    ti_sig = AssetSignature.query.filter_by(person_key=TI_KEY).first()
    return render_template("assets/termo.html", a=data, data_extenso=data_extenso,
                           saved_signature=(sig.data_url if sig else ""),
                           signed_at=(sig.signed_at if sig else None),
                           ti_signature=(ti_sig.data_url if ti_sig else ""))


def _upsert_signature(key: str, name: str, data_url: str) -> AssetSignature:
    sig = AssetSignature.query.filter_by(person_key=key).first()
    if sig is None:
        sig = AssetSignature(person_key=key, person_name=name, data_url=data_url)
        db.session.add(sig)
    else:
        sig.data_url = data_url
        sig.person_name = name
    return sig


@bp.route("/<path:name>/signature", methods=["POST"])
def save_signature(name):
    """Salva a assinatura do colaborador e registra um comprovante de entrega
    (congela os equipamentos + a assinatura naquele momento)."""
    data_url = (request.form.get("signature") or "").strip()
    if not _valid_signature(data_url):
        return jsonify(ok=False, error="assinatura inválida"), 400
    key = _sig_key(name)
    # Não deixa um "colaborador" cujo nome normalize para a chave reservada
    # sobrescrever a assinatura única do Responsável de TI.
    if key == TI_KEY:
        return jsonify(ok=False, error="nome reservado"), 400
    _upsert_signature(key, name, data_url)

    # Comprovante de entrega — evita duplicar se nada mudou desde o último.
    data = assets.assets_for(name)
    itens = _termo_itens(data)
    itens_json = json.dumps(itens, ensure_ascii=False)
    last = (AssetTermo.query.filter_by(person_key=key)
            .order_by(AssetTermo.signed_at.desc(), AssetTermo.id.desc()).first())
    if not (last and last.equipamentos == itens_json and last.signature == data_url):
        db.session.add(AssetTermo(person_key=key, person_name=name,
                                  sector=data.get("sector") or None,
                                  equipamentos=itens_json, signature=data_url))
    db.session.commit()
    audit.record("update", "asset_signature", None, f"Assinou o termo de {name}")
    return jsonify(ok=True)


@bp.route("/ti-signature", methods=["POST"])
def save_ti_signature():
    """Salva/atualiza a assinatura (única) do Responsável de TI, reutilizada em
    todos os termos."""
    data_url = (request.form.get("signature") or "").strip()
    if not _valid_signature(data_url):
        return jsonify(ok=False, error="assinatura inválida"), 400
    _upsert_signature(TI_KEY, "Responsável de TI", data_url)
    db.session.commit()
    audit.record("update", "asset_signature", None, "Atualizou a assinatura do Responsável de TI")
    return jsonify(ok=True)


@bp.route("/<path:name>/termos")
def termos_history(name):
    """Histórico de termos/comprovantes assinados por uma pessoa."""
    key = _sig_key(name)
    termos = (AssetTermo.query.filter_by(person_key=key)
              .order_by(AssetTermo.signed_at.desc(), AssetTermo.id.desc()).all())
    for t in termos:
        try:
            t.itens = json.loads(t.equipamentos or "[]")
        except (ValueError, TypeError):
            t.itens = []
    return render_template("assets/termos.html", name=name, termos=termos)
