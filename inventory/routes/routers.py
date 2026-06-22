# inventory/routes/routers.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from ..extensions import db
from ..repositories import router_repo
from ..forms.router import RouterForm
from ..models.router import Router

bp = Blueprint("routers", __name__)


def _to_kwargs(form: RouterForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        label=s(form.label.data),
        brand=s(form.brand.data),
        model=(form.model.data or "").strip(),
        location=s(form.location.data),
        serial_number=s(form.serial_number.data),
        patrimony=s(form.patrimony.data),
        ip_address=s(form.ip_address.data),
        mac_address=s(form.mac_address.data),
        admin_user=s(form.admin_user.data),
        admin_password=s(form.admin_password.data),
        ssid=s(form.ssid.data),
        wifi_password=s(form.wifi_password.data),
        ssid_guest=s(form.ssid_guest.data),
        wifi_password_guest=s(form.wifi_password_guest.data),
        mac_filtering=bool(form.mac_filtering.data),
        linked_macs=s(form.linked_macs.data),
        status=form.status.data or "em_uso",
        notes=s(form.notes.data),
        label_applied=bool(form.label_applied.data),
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    items = router_repo.list_routers(q or None, status or None)
    counts = dict(db.session.query(Router.status, func.count(Router.id))
                  .group_by(Router.status).all())
    totals = {
        "em_uso": counts.get("em_uso", 0),
        "disponivel": counts.get("disponivel", 0),
        "manutencao": counts.get("manutencao", 0),
        "inativo": counts.get("inativo", 0),
        "total": sum(counts.values()),
    }
    return render_template("routers/list.html", items=items, q=q, status=status, totals=totals)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = RouterForm()
    if form.validate_on_submit():
        router_repo.create_router(**_to_kwargs(form))
        flash("Roteador cadastrado!", "success")
        return redirect(url_for("routers.list_view"))
    return render_template("routers/form.html", form=form, title="Novo Roteador")


@bp.route("/<int:rid>/edit", methods=["GET", "POST"])
@login_required
def edit(rid):
    r = router_repo.get_router(rid)
    form = RouterForm(obj=r)
    if form.validate_on_submit():
        router_repo.update_router(r, **_to_kwargs(form))
        flash("Roteador atualizado!", "success")
        return redirect(url_for("routers.list_view"))
    return render_template("routers/form.html", form=form, title="Editar Roteador")


@bp.route("/<int:rid>/delete", methods=["POST"])
@login_required
def delete(rid):
    r = router_repo.get_router(rid)
    router_repo.delete_router(r)
    flash("Roteador excluído.", "success")
    return redirect(url_for("routers.list_view"))
