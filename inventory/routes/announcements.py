# inventory/routes/announcements.py — Central de Avisos (mural interno)
#
# Mural de recados da empresa. Apenas administradores publicam/editam; os demais
# usuários só visualizam. Para o perfil comum, esta é a tela inicial pós-login.
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..extensions import db
from ..models.announcement import Announcement
from ..forms.announcement import AnnouncementForm
from ..services import audit

bp = Blueprint("announcements", __name__)


@bp.before_request
@login_required
def _require_login():
    # Todo usuário logado pode ver o mural; as ações de escrita checam admin.
    pass


def _admin_only():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def list_view():
    # Admin enxerga inclusive os despublicados (para gerenciar); usuário comum
    # vê só os ativos.
    query = Announcement.query
    if not current_user.is_admin:
        query = query.filter(Announcement.is_active.is_(True))
    items = query.order_by(
        Announcement.is_pinned.desc(),
        Announcement.created_at.desc(),
    ).all()
    return render_template("announcements/list.html", items=items,
                           is_admin=current_user.is_admin)


@bp.route("/new", methods=["GET", "POST"])
def new():
    _admin_only()
    form = AnnouncementForm()
    if form.validate_on_submit():
        a = Announcement(
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            level=form.level.data or "info",
            is_pinned=bool(form.is_pinned.data),
            is_active=bool(form.is_active.data),
            author_id=current_user.id,
        )
        db.session.add(a)
        db.session.commit()
        audit.record("create", "announcement", a.id, f"Publicou aviso: {a.title}")
        flash("Aviso publicado!", "success")
        return redirect(url_for("announcements.list_view"))
    return render_template("announcements/form.html", form=form, title="Novo Aviso")


@bp.route("/<int:aid>/edit", methods=["GET", "POST"])
def edit(aid):
    _admin_only()
    a = Announcement.query.get_or_404(aid)
    form = AnnouncementForm(obj=a)
    if form.validate_on_submit():
        a.title = form.title.data.strip()
        a.body = form.body.data.strip()
        a.level = form.level.data or "info"
        a.is_pinned = bool(form.is_pinned.data)
        a.is_active = bool(form.is_active.data)
        db.session.commit()
        audit.record("update", "announcement", a.id, f"Editou aviso: {a.title}")
        flash("Aviso atualizado!", "success")
        return redirect(url_for("announcements.list_view"))
    return render_template("announcements/form.html", form=form,
                           title="Editar Aviso")


@bp.route("/<int:aid>/toggle-active", methods=["POST"])
def toggle_active(aid):
    _admin_only()
    a = Announcement.query.get_or_404(aid)
    a.is_active = not bool(a.is_active)
    db.session.commit()
    flash(f"Aviso {'publicado' if a.is_active else 'despublicado'}.", "success")
    return redirect(url_for("announcements.list_view"))


@bp.route("/<int:aid>/toggle-pin", methods=["POST"])
def toggle_pin(aid):
    _admin_only()
    a = Announcement.query.get_or_404(aid)
    a.is_pinned = not bool(a.is_pinned)
    db.session.commit()
    flash(f"Aviso {'fixado' if a.is_pinned else 'desafixado'}.", "success")
    return redirect(url_for("announcements.list_view"))


@bp.route("/<int:aid>/delete", methods=["POST"])
def delete(aid):
    _admin_only()
    a = Announcement.query.get_or_404(aid)
    audit.record("delete", "announcement", a.id, f"Excluiu aviso: {a.title}")
    db.session.delete(a)
    db.session.commit()
    flash("Aviso excluído.", "success")
    return redirect(url_for("announcements.list_view"))
