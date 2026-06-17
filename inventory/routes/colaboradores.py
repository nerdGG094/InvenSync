# inventory/routes/colaboradores.py — cadastro central de colaboradores (admin)
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..extensions import db
from ..models.colaborador import Colaborador
from ..forms.colaborador import ColaboradorForm

bp = Blueprint("colaboradores", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _clean(v):
    v = (v or "").strip()
    return v or None


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    query = Colaborador.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Colaborador.name.ilike(like)) | (Colaborador.department.ilike(like))
        )
    items = query.order_by(Colaborador.name).all()
    return render_template("colaboradores/list.html", items=items, q=q)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = ColaboradorForm()
    if form.validate_on_submit():
        nome = form.name.data.strip()
        if Colaborador.query.filter(db.func.lower(Colaborador.name) == nome.lower()).first():
            flash("Já existe um colaborador com esse nome.", "warning")
        else:
            c = Colaborador(
                name=nome,
                department=_clean(form.department.data),
                email=_clean(form.email.data),
                is_active=bool(form.is_active.data),
            )
            db.session.add(c)
            db.session.commit()
            flash("Colaborador cadastrado!", "success")
            return redirect(url_for("colaboradores.list_view"))
    return render_template("colaboradores/form.html", form=form, title="Novo Colaborador")


@bp.route("/<int:cid>/edit", methods=["GET", "POST"])
def edit(cid):
    c = Colaborador.query.get_or_404(cid)
    form = ColaboradorForm(obj=c)
    if form.validate_on_submit():
        nome = form.name.data.strip()
        dup = Colaborador.query.filter(db.func.lower(Colaborador.name) == nome.lower()).first()
        if dup and dup.id != c.id:
            flash("Já existe um colaborador com esse nome.", "warning")
        else:
            c.name = nome
            c.department = _clean(form.department.data)
            c.email = _clean(form.email.data)
            c.is_active = bool(form.is_active.data)
            db.session.commit()
            flash("Colaborador atualizado!", "success")
            return redirect(url_for("colaboradores.list_view"))
    return render_template("colaboradores/form.html", form=form, title="Editar Colaborador")


@bp.route("/<int:cid>/toggle-active", methods=["POST"])
def toggle_active(cid):
    c = Colaborador.query.get_or_404(cid)
    c.is_active = not bool(c.is_active)
    db.session.commit()
    flash(f"Colaborador “{c.name}” {'ativado' if c.is_active else 'inativado'}.", "success")
    return redirect(url_for("colaboradores.list_view"))


@bp.route("/<int:cid>/delete", methods=["POST"])
def delete(cid):
    c = Colaborador.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash("Colaborador excluído.", "success")
    return redirect(url_for("colaboradores.list_view"))
