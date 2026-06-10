# inventory/routes/machines.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from ..extensions import db
from ..repositories import machine_repo
from ..forms.machines import MachineForm
from ..models.machine import Machine

bp = Blueprint("machines", __name__)


def _form_to_kwargs(form: MachineForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        kind=form.kind.data or "computador",
        name=s(form.name.data),
        brand=s(form.brand.data),
        model=s(form.model.data),
        assigned_user=s(form.assigned_user.data),
        ip_address=s(form.ip_address.data),
        sector=s(form.sector.data),
        patrimony=s(form.patrimony.data),
        serial_number=s(form.serial_number.data),
        notes=s(form.notes.data),
        is_active=bool(form.is_active.data),
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
    return render_template("machines/list.html", items=items, q=q, kind=kind, totals=totals)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = MachineForm()
    if request.method == "GET" and not form.kind.data:
        form.kind.data = request.args.get("kind") or "computador"
    if form.validate_on_submit():
        machine_repo.create_machine(**_form_to_kwargs(form))
        flash("Máquina cadastrada!", "success")
        return redirect(url_for("machines.list_view"))
    return render_template("machines/form.html", form=form, title="Nova Máquina")


@bp.route("/<int:mid>/edit", methods=["GET", "POST"])
@login_required
def edit(mid):
    m = machine_repo.get_machine(mid)
    form = MachineForm(obj=m)
    if form.validate_on_submit():
        machine_repo.update_machine(m, **_form_to_kwargs(form))
        flash("Máquina atualizada!", "success")
        return redirect(url_for("machines.list_view"))
    return render_template("machines/form.html", form=form, title="Editar Máquina")


@bp.route("/<int:mid>/delete", methods=["POST"])
@login_required
def delete(mid):
    m = machine_repo.get_machine(mid)
    machine_repo.delete_machine(m)
    flash("Máquina excluída.", "success")
    return redirect(url_for("machines.list_view"))
