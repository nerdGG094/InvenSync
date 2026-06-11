# inventory/routes/mobile.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from ..extensions import db
from ..repositories import mobile_repo
from ..forms.mobile import MobileForm
from ..models.mobile import MobileDevice
from ..services import people

bp = Blueprint("mobile", __name__)


def _populate(form: MobileForm):
    form.assigned_employee.choices = people.user_choices()


def _to_kwargs(form: MobileForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        brand=s(form.brand.data),
        model=(form.model.data or "").strip(),
        phone_number=s(form.phone_number.data),
        carrier=s(form.carrier.data),
        plan=s(form.plan.data),
        imei=s(form.imei.data),
        serial_number=s(form.serial_number.data),
        assigned_employee=s(form.assigned_employee.data),
        sector=s(form.sector.data),
        patrimony=s(form.patrimony.data),
        status=form.status.data or "em_uso",
        handed_at=form.handed_at.data,
        notes=s(form.notes.data),
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    items = mobile_repo.list_mobiles(q or None, status or None)
    counts = dict(db.session.query(MobileDevice.status, func.count(MobileDevice.id))
                  .group_by(MobileDevice.status).all())
    totals = {
        "em_uso": counts.get("em_uso", 0),
        "disponivel": counts.get("disponivel", 0),
        "manutencao": counts.get("manutencao", 0),
        "inativo": counts.get("inativo", 0),
        "total": sum(counts.values()),
    }
    return render_template("mobile/list.html", items=items, q=q, status=status, totals=totals)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = MobileForm()
    _populate(form)
    if form.validate_on_submit():
        mobile_repo.create_mobile(**_to_kwargs(form))
        flash("Celular cadastrado!", "success")
        return redirect(url_for("mobile.list_view"))
    return render_template("mobile/form.html", form=form, title="Novo Celular",
                           users_info=people.users_sector_map())


@bp.route("/<int:mid>/edit", methods=["GET", "POST"])
@login_required
def edit(mid):
    m = mobile_repo.get_mobile(mid)
    form = MobileForm(obj=m)
    _populate(form)
    if m.assigned_employee and m.assigned_employee not in [c[0] for c in form.assigned_employee.choices]:
        form.assigned_employee.choices.append((m.assigned_employee, m.assigned_employee))
    if request.method == "GET":
        form.assigned_employee.data = m.assigned_employee or ""
    if form.validate_on_submit():
        mobile_repo.update_mobile(m, **_to_kwargs(form))
        flash("Celular atualizado!", "success")
        return redirect(url_for("mobile.list_view"))
    return render_template("mobile/form.html", form=form, title="Editar Celular",
                           users_info=people.users_sector_map())


@bp.route("/<int:mid>/delete", methods=["POST"])
@login_required
def delete(mid):
    m = mobile_repo.get_mobile(mid)
    mobile_repo.delete_mobile(m)
    flash("Celular excluído.", "success")
    return redirect(url_for("mobile.list_view"))
