# inventory/routes/cleanings.py
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from ..repositories import cleaning_repo
from ..forms.machines import CleaningForm
from ..models.machine import Machine
from ..services.pagination import paginate

bp = Blueprint("cleanings", __name__)


def _machine_label(m: Machine) -> str:
    kinds = {"computador": "Computador", "notebook": "Notebook", "impressora": "Impressora"}
    parts = [m.model or "—"]
    if m.assigned_user:
        parts.append(m.assigned_user)
    return f"{kinds.get(m.kind, m.kind)} · " + " · ".join(parts)


def _populate(form: CleaningForm):
    machines = Machine.query.order_by(Machine.assigned_user.asc().nullslast(),
                                      Machine.model.asc()).all()
    form.machine_id.choices = [(m.id, _machine_label(m)) for m in machines]


def _to_kwargs(form: CleaningForm) -> dict:
    return dict(
        machine_id=form.machine_id.data,
        started_at=form.started_at.data,
        finished_at=form.finished_at.data,
        executed_by=(form.executed_by.data or "").strip() or None,
        period_days=form.period_days.data,
        next_date=form.next_date.data,
        notes=(form.notes.data or "").strip() or None,
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    machine_id = request.args.get("machine_id", type=int)
    items = cleaning_repo.list_cleanings(q or None, machine_id)
    hoje = date.today()
    items, pag = paginate(items)
    return render_template("cleanings/list.html", items=items, q=q, pag=pag,
                           machine_id=machine_id, hoje=hoje)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = CleaningForm()
    _populate(form)
    if not form.machine_id.choices:
        flash("Cadastre uma máquina antes de registrar uma limpeza.", "warning")
        return redirect(url_for("machines.new"))

    if request.method == "GET":
        form.started_at.data = datetime.now().replace(second=0, microsecond=0)
        if not form.executed_by.data:
            form.executed_by.data = current_user.name
        mid = request.args.get("machine_id", type=int)
        if mid:
            form.machine_id.data = mid

    if form.validate_on_submit():
        data = _to_kwargs(form)
        # Calcula próxima limpeza se houver periodicidade e nenhuma data informada
        if not data["next_date"] and data["period_days"] and data["started_at"]:
            data["next_date"] = (data["started_at"] + timedelta(days=data["period_days"])).date()
        cleaning_repo.create_cleaning(**data)
        flash("Limpeza registrada!", "success")
        return redirect(url_for("cleanings.list_view"))
    return render_template("cleanings/form.html", form=form, title="Nova Limpeza")


@bp.route("/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def edit(cid):
    c = cleaning_repo.get_cleaning(cid)
    form = CleaningForm(obj=c)
    _populate(form)
    if request.method == "GET":
        form.machine_id.data = c.machine_id

    if form.validate_on_submit():
        data = _to_kwargs(form)
        if not data["next_date"] and data["period_days"] and data["started_at"]:
            data["next_date"] = (data["started_at"] + timedelta(days=data["period_days"])).date()
        cleaning_repo.update_cleaning(c, **data)
        flash("Limpeza atualizada!", "success")
        return redirect(url_for("cleanings.list_view"))
    return render_template("cleanings/form.html", form=form, title="Editar Limpeza")


@bp.route("/<int:cid>/delete", methods=["POST"])
@login_required
def delete(cid):
    c = cleaning_repo.get_cleaning(cid)
    cleaning_repo.delete_cleaning(c)
    flash("Limpeza excluída.", "success")
    return redirect(url_for("cleanings.list_view"))
