from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from ..extensions import db
from ..models.user import User
from ..forms.users import UserForm

bp = Blueprint("users", __name__)

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper

@bp.route("")
@login_required
@admin_required
def list_view():
    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter((User.name.ilike(like)) | (User.email.ilike(like)))
    users = query.order_by(User.name).all()
    return render_template("users/list.html", users=users, q=q)

@bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    form = UserForm()
    if form.validate_on_submit():
        # checa e-mail único
        if User.query.filter_by(email=form.email.data.strip()).first():
            flash("E-mail já cadastrado.", "warning")
        else:
            u = User(
                name=form.name.data.strip(),
                email=form.email.data.strip(),
                is_admin=bool(form.is_admin.data),
            )
            if form.password.data:
                u.set_password(form.password.data)
            else:
                flash("Defina uma senha para o usuário.", "warning")
                return render_template("users/form.html", form=form, title="Novo Usuário")
            db.session.add(u)
            db.session.commit()
            flash("Usuário criado!", "success")
            return redirect(url_for("users.list_view"))
    return render_template("users/form.html", form=form, title="Novo Usuário")

@bp.route("/<int:uid>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit(uid):
    u = User.query.get_or_404(uid)
    form = UserForm(obj=u)
    if form.validate_on_submit():
        # e-mail único (permitindo o mesmo do próprio usuário)
        existing = User.query.filter_by(email=form.email.data.strip()).first()
        if existing and existing.id != u.id:
            flash("E-mail já em uso por outro usuário.", "warning")
        else:
            u.name = form.name.data.strip()
            u.email = form.email.data.strip()
            u.is_admin = bool(form.is_admin.data)
            if form.password.data:
                u.set_password(form.password.data)
            db.session.commit()
            flash("Usuário atualizado!", "success")
            return redirect(url_for("users.list_view"))
    return render_template("users/form.html", form=form, title="Editar Usuário")

@bp.route("/<int:uid>/delete", methods=["POST"])
@login_required
@admin_required
def delete(uid):
    u = User.query.get_or_404(uid)
    if u.id == current_user.id:
        flash("Você não pode excluir a si mesmo.", "warning")
        return redirect(url_for("users.list_view"))
    db.session.delete(u)
    db.session.commit()
    flash("Usuário excluído.", "success")
    return redirect(url_for("users.list_view"))
