# inventory/routes/machines.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from ..extensions import db
from ..repositories import machine_repo
from ..forms.machines import MachineForm
from ..models.machine import Machine
from ..services import people, patrimony

bp = Blueprint("machines", __name__)


def _group_by_sector(items: list) -> list:
    """Agrupa máquinas por setor (alfabético; 'Sem setor' por último)."""
    grupos_map = {}
    for it in items:
        setor = (it.sector or "").strip()
        grupos_map.setdefault(setor, []).append(it)
    nomeados = sorted((s for s in grupos_map if s), key=lambda s: s.lower())
    ordem = nomeados + ([""] if "" in grupos_map else [])
    return [{"name": s or None, "items": grupos_map[s]} for s in ordem]


def _form_to_kwargs(form: MachineForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    # Setor automático: se ficou em branco, busca do cadastro do colaborador.
    sector = s(form.sector.data)
    if not sector and form.assigned_user.data:
        sector = people.sector_for(form.assigned_user.data) or None
    return dict(
        kind=form.kind.data or "computador",
        name=s(form.name.data),
        brand=s(form.brand.data),
        model=s(form.model.data),
        assigned_user=s(form.assigned_user.data),
        ip_address=s(form.ip_address.data),
        sector=sector,
        patrimony=s(form.patrimony.data),
        serial_number=s(form.serial_number.data),
        notes=s(form.notes.data),
        is_active=bool(form.is_active.data),
        label_applied=bool(form.label_applied.data),
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    kind = (request.args.get("kind") or "").strip()
    items = machine_repo.list_machines(q or None, kind or None)

    # Contagem por tipo (sobre toda a base, para os cartões)
    counts = dict(
        db.session.query(Machine.kind, func.count(Machine.id))
        .group_by(Machine.kind).all()
    )
    totals = {
        "computador": counts.get("computador", 0),
        "notebook": counts.get("notebook", 0),
        "impressora": counts.get("impressora", 0),
        "total": sum(counts.values()),
    }
    grupos = _group_by_sector(items)
    return render_template("machines/list.html", items=items, q=q, kind=kind,
                           totals=totals, grupos=grupos)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = MachineForm()
    form.assigned_user.choices = people.user_choices("— Selecione —")
    if request.method == "GET":
        if not form.kind.data:
            form.kind.data = request.args.get("kind") or "computador"
        # Sugere um nº de patrimônio automático (editável pelo usuário).
        if not form.patrimony.data:
            form.patrimony.data = patrimony.next_patrimony()
    if form.validate_on_submit():
        machine_repo.create_machine(**_form_to_kwargs(form))
        flash("Máquina cadastrada!", "success")
        return redirect(url_for("machines.list_view"))
    return render_template("machines/form.html", form=form, title="Nova Máquina",
                           users_info=people.users_sector_map())


@bp.route("/<int:mid>/edit", methods=["GET", "POST"])
@login_required
def edit(mid):
    m = machine_repo.get_machine(mid)
    form = MachineForm(obj=m)
    form.assigned_user.choices = people.user_choices("— Selecione —")
    # Garante que o responsável atual apareça mesmo se o colaborador foi removido/inativado.
    if m.assigned_user and m.assigned_user not in [c[0] for c in form.assigned_user.choices]:
        form.assigned_user.choices.append((m.assigned_user, m.assigned_user))
    if form.validate_on_submit():
        machine_repo.update_machine(m, **_form_to_kwargs(form))
        flash("Máquina atualizada!", "success")
        return redirect(url_for("machines.list_view"))
    return render_template("machines/form.html", form=form, title="Editar Máquina",
                           users_info=people.users_sector_map())


@bp.route("/<int:mid>/delete", methods=["POST"])
@login_required
def delete(mid):
    m = machine_repo.get_machine(mid)
    machine_repo.delete_machine(m)
    flash("Máquina excluída.", "success")
    return redirect(url_for("machines.list_view"))
