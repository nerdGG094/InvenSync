# inventory/routes/chips.py — controle de chips (linhas/SIM) da empresa
#
# O item controlado é a LINHA, não o aparelho. Caso central: chip da empresa
# usado no celular PARTICULAR do funcionário. Quando o chip está num aparelho
# da empresa, liga-se (opcional) a um registro de Celular.
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..repositories import chip_repo
from ..forms.chip import ChipForm
from ..models.chip import SimChip
from ..models.mobile import MobileDevice
from ..services import people

_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]

bp = Blueprint("chips", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _mobile_choices() -> list:
    """Choices do seletor de aparelho da empresa (para chips em celular nosso)."""
    out = [("", "— Nenhum —")]
    for d in MobileDevice.query.order_by(MobileDevice.model).all():
        rotulo = f"{(d.brand or '').strip()} {d.model}".strip()
        if d.phone_number:
            rotulo += f" ({d.phone_number})"
        out.append((str(d.id), rotulo))
    return out


def _populate(form: ChipForm):
    form.assigned_employee.choices = people.user_choices()
    form.mobile_id.choices = _mobile_choices()


def _to_kwargs(form: ChipForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    usage = form.usage.data or "particular"
    # Vínculo a aparelho só faz sentido quando o chip está num celular da empresa.
    mobile_id = None
    if usage == "aparelho_empresa" and (form.mobile_id.data or "").strip():
        try:
            mobile_id = int(form.mobile_id.data)
        except (TypeError, ValueError):
            mobile_id = None
    # Setor automático: se ficou em branco, busca do cadastro do colaborador.
    sector = s(form.sector.data)
    if not sector and form.assigned_employee.data:
        sector = people.sector_for(form.assigned_employee.data) or None
    return dict(
        phone_number=(form.phone_number.data or "").strip(),
        carrier=s(form.carrier.data),
        plan=s(form.plan.data),
        iccid=s(form.iccid.data),
        usage=usage,
        assigned_employee=s(form.assigned_employee.data),
        sector=sector,
        mobile_id=mobile_id,
        handed_at=form.handed_at.data,
        notes=s(form.notes.data),
    )


def _group_by_sector(items: list) -> list:
    """Agrupa por setor (alfabético; 'Sem setor' por último)."""
    grupos_map = {}
    for it in items:
        setor = (it.sector or "").strip()
        grupos_map.setdefault(setor, []).append(it)
    nomeados = sorted((s for s in grupos_map if s), key=lambda s: s.lower())
    ordem = nomeados + ([""] if "" in grupos_map else [])
    return [{"name": s or None, "items": grupos_map[s]} for s in ordem]


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    usage = (request.args.get("usage") or "").strip()
    items = chip_repo.list_chips(q or None, usage or None)
    counts = dict(db.session.query(SimChip.usage, func.count(SimChip.id))
                  .group_by(SimChip.usage).all())
    totals = {
        "particular": counts.get("particular", 0),
        "aparelho_empresa": counts.get("aparelho_empresa", 0),
        "disponivel": counts.get("disponivel", 0),
        "cancelado": counts.get("cancelado", 0),
        "total": sum(counts.values()),
    }
    grupos = _group_by_sector(items)
    return render_template("chips/list.html", items=items, q=q, usage=usage,
                           totals=totals, grupos=grupos,
                           labels=SimChip.USAGE_LABELS)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = ChipForm()
    _populate(form)
    if form.validate_on_submit():
        chip_repo.create_chip(**_to_kwargs(form))
        flash("Chip cadastrado!", "success")
        return redirect(url_for("chips.list_view"))
    return render_template("chips/form.html", form=form, title="Novo Chip",
                           users_info=people.users_sector_map())


@bp.route("/<int:cid>/edit", methods=["GET", "POST"])
def edit(cid):
    c = chip_repo.get_chip(cid)
    form = ChipForm(obj=c)
    _populate(form)
    # Garante que o responsável atual apareça, mesmo se foi removido/inativado.
    if c.assigned_employee and c.assigned_employee not in [x[0] for x in form.assigned_employee.choices]:
        form.assigned_employee.choices.append((c.assigned_employee, c.assigned_employee))
    if request.method == "GET":
        form.assigned_employee.data = c.assigned_employee or ""
        form.mobile_id.data = str(c.mobile_id) if c.mobile_id else ""
    if form.validate_on_submit():
        chip_repo.update_chip(c, **_to_kwargs(form))
        flash("Chip atualizado!", "success")
        return redirect(url_for("chips.list_view"))
    return render_template("chips/form.html", form=form, title="Editar Chip",
                           users_info=people.users_sector_map())


@bp.route("/<int:cid>/delete", methods=["POST"])
def delete(cid):
    c = chip_repo.get_chip(cid)
    chip_repo.delete_chip(c)
    flash("Chip excluído.", "success")
    return redirect(url_for("chips.list_view"))


@bp.route("/export")
def export():
    from ..services.exports import xlsx_response
    q = (request.args.get("q") or "").strip()
    usage = (request.args.get("usage") or "").strip()
    items = chip_repo.list_chips(q or None, usage or None)
    headers = ["Número", "Operadora", "Plano", "ICCID", "Uso", "Responsável",
               "Setor", "Aparelho", "Entregue em"]
    rows = []
    for c in items:
        rows.append([
            c.phone_number, c.carrier or "", c.plan or "", c.iccid or "",
            c.usage_label, c.assigned_employee or "", c.sector or "",
            (f"{c.mobile.brand or ''} {c.mobile.model}".strip() if c.mobile else ""),
            c.handed_at.strftime("%d/%m/%Y") if c.handed_at else "",
        ])
    return xlsx_response("Chips", headers, rows, filename="chips_linhas")


@bp.route("/<int:cid>/termo")
def termo(cid):
    c = chip_repo.get_chip(cid)
    now = datetime.now()
    data_extenso = f"{now.day} de {_MESES[now.month - 1]} de {now.year}"
    return render_template("chips/termo.html", c=c, data_extenso=data_extenso)
