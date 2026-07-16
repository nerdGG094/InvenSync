# inventory/routes/smartplugs.py — Tomadas inteligentes Tuya/NeoAvant (Admin)
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify)
from flask_login import login_required, current_user

from ..extensions import db
from ..models.smart_plug import SmartPlug
from ..forms.smart_plug import SmartPlugForm
from ..services import audit, crypto, tuya

bp = Blueprint("smartplugs", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def list_view():
    plugs = SmartPlug.query.order_by(SmartPlug.name).all()
    return render_template("smartplugs/list.html", plugs=plugs)


def _apply(form: SmartPlugForm, plug: SmartPlug):
    plug.name = form.name.data.strip()
    plug.location = (form.location.data or "").strip() or None
    plug.device_id = form.device_id.data.strip()
    plug.ip_address = (form.ip_address.data or "").strip() or None
    plug.version = form.version.data or "3.3"
    plug.switch_dp = (form.switch_dp.data or "1").strip() or "1"
    plug.is_active = bool(form.is_active.data)
    plug.notes = (form.notes.data or "").strip() or None
    # Local key só é atualizada se preenchida; guardada cifrada (VAULT_KEY).
    if form.local_key.data:
        plug.local_key = crypto.encrypt(form.local_key.data.strip())


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = SmartPlugForm()
    if form.validate_on_submit():
        plug = SmartPlug()
        _apply(form, plug)
        db.session.add(plug)
        db.session.commit()
        audit.record("create", "smart_plug", plug.id, f"Cadastrou tomada '{plug.name}'")
        flash("Tomada cadastrada.", "success")
        return redirect(url_for("smartplugs.list_view"))
    return render_template("smartplugs/form.html", form=form, title="Nova Tomada", plug=None)


@bp.route("/<int:pid>/edit", methods=["GET", "POST"])
def edit(pid):
    plug = db.get_or_404(SmartPlug, pid)
    form = SmartPlugForm(obj=plug)
    if request.method == "GET":
        form.local_key.data = ""    # nunca ecoa a chave salva
    if form.validate_on_submit():
        _apply(form, plug)
        db.session.commit()
        audit.record("update", "smart_plug", plug.id, f"Editou tomada '{plug.name}'")
        flash("Tomada atualizada.", "success")
        return redirect(url_for("smartplugs.list_view"))
    return render_template("smartplugs/form.html", form=form,
                           title=f"Editar {plug.name}", plug=plug)


@bp.route("/<int:pid>/delete", methods=["POST"])
def delete(pid):
    plug = db.get_or_404(SmartPlug, pid)
    audit.record("delete", "smart_plug", plug.id, f"Excluiu tomada '{plug.name}'")
    db.session.delete(plug)
    db.session.commit()
    flash("Tomada removida.", "success")
    return redirect(url_for("smartplugs.list_view"))


@bp.route("/<int:pid>/status")
def status(pid):
    """Estado ao vivo (chamada de rede à tomada) — consumido via AJAX."""
    plug = db.get_or_404(SmartPlug, pid)
    return jsonify(tuya.get_status(plug))


@bp.route("/<int:pid>/toggle", methods=["POST"])
def toggle(pid):
    plug = db.get_or_404(SmartPlug, pid)
    on = (request.form.get("on") or "").lower() in ("1", "true", "on")
    res = tuya.set_state(plug, on)
    if res.get("ok"):
        audit.record("update", "smart_plug", plug.id,
                     f"{'Ligou' if on else 'Desligou'} a tomada '{plug.name}'")
    return jsonify(res)
