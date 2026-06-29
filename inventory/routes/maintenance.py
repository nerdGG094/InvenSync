# inventory/routes/maintenance.py
from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from ..repositories import maintenance_repo
from ..forms.maintenance import MaintenanceForm, KIND_CHOICES
from ..models.machine import Machine
from ..models.machine_maintenance import MachineMaintenance
from ..extensions import db
from ..services import audit
from ..services.exports import xlsx_response
from ..services.pagination import paginate

bp = Blueprint("maintenance", __name__)

KINDS = {"computador": "Computador", "notebook": "Notebook", "impressora": "Impressora"}


def _machine_label(m: Machine) -> str:
    parts = [m.model or "—"]
    if m.assigned_user:
        parts.append(m.assigned_user)
    return f"{KINDS.get(m.kind, m.kind)} · " + " · ".join(parts)


def _populate(form: MaintenanceForm):
    machines = Machine.query.order_by(Machine.assigned_user.asc().nullslast(),
                                      Machine.model.asc()).all()
    form.machine_id.choices = [(m.id, _machine_label(m)) for m in machines]


def _to_kwargs(form: MaintenanceForm) -> dict:
    return dict(
        machine_id=form.machine_id.data,
        date=form.date.data,
        kind=form.kind.data or "corretiva",
        description=(form.description.data or "").strip(),
        parts=(form.parts.data or "").strip() or None,
        performed_by=(form.performed_by.data or "").strip() or None,
        cost=form.cost.data,
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    machine_id = request.args.get("machine_id", type=int)
    kind = (request.args.get("kind") or "").strip()
    items = maintenance_repo.list_maintenances(q or None, machine_id, kind or None)
    total_cost = sum((m.cost or 0) for m in items)
    items, pag = paginate(items)
    return render_template("maintenance/list.html", items=items, q=q, pag=pag,
                           machine_id=machine_id, kind=kind, total_cost=total_cost,
                           kind_choices=KIND_CHOICES)


@bp.route("/export")
@login_required
def export():
    q = (request.args.get("q") or "").strip()
    machine_id = request.args.get("machine_id", type=int)
    kind = (request.args.get("kind") or "").strip()
    items = maintenance_repo.list_maintenances(q or None, machine_id, kind or None)
    kind_lbl = dict(KIND_CHOICES)
    headers = ["Data", "Máquina", "Usuário", "Tipo", "Descrição", "Peças", "Executado por", "Custo (R$)"]
    rows = []
    for m in items:
        rows.append([
            m.date.strftime("%d/%m/%Y") if m.date else "",
            m.machine.model if m.machine else "",
            m.machine.assigned_user if m.machine else "",
            kind_lbl.get(m.kind, m.kind), m.description or "", m.parts or "",
            m.performed_by or "", float(m.cost) if m.cost is not None else "",
        ])
    audit.record("export", "maintenance", None, f"Exportou {len(rows)} manutenção(ões)")
    return xlsx_response("Manutencoes", headers, rows, filename="manutencoes")


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = MaintenanceForm()
    _populate(form)
    if not form.machine_id.choices:
        flash("Cadastre uma máquina antes de registrar manutenção.", "warning")
        return redirect(url_for("machines.new"))
    if request.method == "GET":
        form.date.data = date.today()
        if not form.performed_by.data:
            form.performed_by.data = current_user.name
        mid = request.args.get("machine_id", type=int)
        if mid:
            form.machine_id.data = mid
    if form.validate_on_submit():
        m = maintenance_repo.create_maintenance(**_to_kwargs(form))
        audit.record("create", "maintenance", m.id, f"Manutenção registrada (máquina #{m.machine_id})")
        flash("Manutenção registrada!", "success")
        return redirect(url_for("maintenance.list_view"))
    return render_template("maintenance/form.html", form=form, title="Nova Manutenção")


@bp.route("/<int:mid>/edit", methods=["GET", "POST"])
@login_required
def edit(mid):
    m = maintenance_repo.get_maintenance(mid)
    form = MaintenanceForm(obj=m)
    _populate(form)
    if request.method == "GET":
        form.machine_id.data = m.machine_id
    if form.validate_on_submit():
        maintenance_repo.update_maintenance(m, **_to_kwargs(form))
        flash("Manutenção atualizada!", "success")
        return redirect(url_for("maintenance.list_view"))
    return render_template("maintenance/form.html", form=form, title="Editar Manutenção")


@bp.route("/<int:mid>/delete", methods=["POST"])
@login_required
def delete(mid):
    m = maintenance_repo.get_maintenance(mid)
    audit.record("delete", "maintenance", m.id, f"Excluiu manutenção (máquina #{m.machine_id})")
    maintenance_repo.delete_maintenance(m)
    flash("Manutenção excluída.", "success")
    return redirect(url_for("maintenance.list_view"))
