# inventory/routes/smartplugs.py — Tomadas inteligentes Tuya/NeoAvant (Admin)
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify)
from flask_login import login_required, current_user

from ..extensions import db
from ..models.smart_plug import SmartPlug
from ..models.smart_plug_schedule import SmartPlugSchedule
from ..forms.smart_plug import SmartPlugForm
from ..services import audit, crypto, tuya

bp = Blueprint("smartplugs", __name__)

# Dias da semana ISO (1=Seg ... 7=Dom) para os checkboxes do agendamento.
DAYS = [("1", "Seg"), ("2", "Ter"), ("3", "Qua"), ("4", "Qui"),
        ("5", "Sex"), ("6", "Sáb"), ("7", "Dom")]


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


# ===== Agendamentos (liga/desliga por horário) =====
@bp.route("/<int:pid>/agendamentos")
def schedules(pid):
    plug = db.get_or_404(SmartPlug, pid)
    regras = sorted(plug.schedules, key=lambda s: (s.hour, s.minute))
    return render_template("smartplugs/schedules.html", plug=plug, regras=regras, days=DAYS)


@bp.route("/<int:pid>/agendamentos/novo", methods=["POST"])
def schedule_add(pid):
    plug = db.get_or_404(SmartPlug, pid)
    action = "on" if (request.form.get("action") == "on") else "off"
    try:
        hour = int(request.form.get("hour"))
        minute = int(request.form.get("minute"))
    except (TypeError, ValueError):
        flash("Horário inválido.", "warning")
        return redirect(url_for("smartplugs.schedules", pid=plug.id))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        flash("Horário fora do intervalo.", "warning")
        return redirect(url_for("smartplugs.schedules", pid=plug.id))
    days = "".join(d for d, _ in DAYS if request.form.get(f"day_{d}"))
    db.session.add(SmartPlugSchedule(plug_id=plug.id, action=action, hour=hour,
                                     minute=minute, days=days))
    db.session.commit()
    audit.record("create", "smart_plug", plug.id,
                 f"Agendou {'ligar' if action == 'on' else 'desligar'} {hour:02d}:{minute:02d} em '{plug.name}'")
    flash("Agendamento criado.", "success")
    return redirect(url_for("smartplugs.schedules", pid=plug.id))


@bp.route("/<int:pid>/agendamentos/<int:sid>/toggle", methods=["POST"])
def schedule_toggle(pid, sid):
    s = SmartPlugSchedule.query.filter_by(id=sid, plug_id=pid).first_or_404()
    s.is_active = not s.is_active
    db.session.commit()
    return redirect(url_for("smartplugs.schedules", pid=pid))


@bp.route("/<int:pid>/agendamentos/<int:sid>/delete", methods=["POST"])
def schedule_delete(pid, sid):
    s = SmartPlugSchedule.query.filter_by(id=sid, plug_id=pid).first_or_404()
    db.session.delete(s)
    db.session.commit()
    flash("Agendamento removido.", "success")
    return redirect(url_for("smartplugs.schedules", pid=pid))
