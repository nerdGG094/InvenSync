# inventory/routes/licenses.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..repositories import license_repo
from ..forms.license import LicenseForm, KIND_CHOICES
from ..services import audit, whatsapp

bp = Blueprint("licenses", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _to_kwargs(form: LicenseForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        name=(form.name.data or "").strip(),
        kind=form.kind.data or "licenca",
        vendor=s(form.vendor.data),
        license_key=s(form.license_key.data),
        seats=form.seats.data,
        assigned_to=s(form.assigned_to.data),
        start_date=form.start_date.data,
        expiry_date=form.expiry_date.data,
        cost=form.cost.data,
        notes=s(form.notes.data),
    )


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    kind = (request.args.get("kind") or "").strip()
    items = license_repo.list_licenses(q or None, kind or None)
    counts = {"vencido": 0, "vencendo": 0, "vigente": 0, "sem_data": 0}
    for o in items:
        counts[o.status] = counts.get(o.status, 0) + 1
    return render_template("licenses/list.html", items=items, q=q, kind=kind,
                           counts=counts, kind_choices=KIND_CHOICES)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = LicenseForm()
    if form.validate_on_submit():
        o = license_repo.create_license(**_to_kwargs(form))
        audit.record("create", "license", o.id, f"Criou licença/garantia '{o.name}'")
        flash("Registro salvo!", "success")
        return redirect(url_for("licenses.list_view"))
    return render_template("licenses/form.html", form=form, title="Nova Licença / Garantia")


@bp.route("/<int:lid>/edit", methods=["GET", "POST"])
def edit(lid):
    o = license_repo.get_license(lid)
    form = LicenseForm(obj=o)
    if form.validate_on_submit():
        license_repo.update_license(o, **_to_kwargs(form))
        flash("Registro atualizado!", "success")
        return redirect(url_for("licenses.list_view"))
    return render_template("licenses/form.html", form=form, title="Editar Licença / Garantia")


@bp.route("/<int:lid>/delete", methods=["POST"])
def delete(lid):
    o = license_repo.get_license(lid)
    audit.record("delete", "license", o.id, f"Excluiu licença/garantia '{o.name}'")
    license_repo.delete_license(o)
    flash("Registro excluído.", "success")
    return redirect(url_for("licenses.list_view"))


@bp.route("/alert", methods=["POST"])
def alert():
    """Envia para a TI (WhatsApp) a lista de itens vencidos/vencendo em 30 dias."""
    days = request.form.get("days", type=int) or 30
    itens = license_repo.expiring_within(days)
    if not itens:
        flash("Nenhuma licença/garantia vencendo no período. Nada a notificar.", "info")
        return redirect(url_for("licenses.list_view"))

    linhas = []
    for o in itens:
        d = o.days_left
        quando = "VENCIDO" if d is not None and d < 0 else f"vence em {d}d"
        linhas.append(f"• {o.name} — {o.expiry_date.strftime('%d/%m/%Y')} ({quando})")
    msg = "⚠️ *Licenças / Garantias a vencer*\n" + "\n".join(linhas)
    whatsapp.notify_ti(msg)
    audit.record("export", "license", None, f"Disparou alerta de {len(itens)} licença(s) por WhatsApp")
    if whatsapp.configured() and whatsapp._enabled():
        flash(f"Alerta enviado à TI ({len(itens)} item(ns)).", "success")
    else:
        flash("WhatsApp não está ativo no .env — o alerta foi montado, mas não enviado.", "warning")
    return redirect(url_for("licenses.list_view"))
