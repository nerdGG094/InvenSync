# inventory/routes/departments.py — cadastro de departamentos / setores (admin)
#
# Padroniza os setores usados no cadastro de colaboradores. O colaborador passa
# a ESCOLHER o departamento numa lista, em vez de digitar livremente — evitando
# divergências de nome. O setor continua armazenado em `User.sector` (texto),
# mas agora sempre vindo desta lista.
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.department import Department
from ..models.user import User
from ..forms.department import DepartmentForm
from ..services.pagination import paginate

bp = Blueprint("departments", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _people_counts() -> dict:
    """{ nome_do_setor_em_minúsculas: nº de colaboradores naquele setor }."""
    counts = {}
    for u in User.query.all():
        s = (u.sector or "").strip().lower()
        if s:
            counts[s] = counts.get(s, 0) + 1
    return counts


def _name_taken(nome, ignore_id=None):
    q = Department.query.filter(db.func.lower(Department.name) == nome.lower())
    if ignore_id is not None:
        q = q.filter(Department.id != ignore_id)
    return q.first() is not None


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    query = Department.query
    if q:
        query = query.filter(Department.name.ilike(f"%{q}%"))
    items = query.order_by(Department.name).all()
    items, pag = paginate(items)
    return render_template("departments/list.html", items=items, q=q, pag=pag,
                           counts=_people_counts())


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = DepartmentForm()
    if form.validate_on_submit():
        nome = form.name.data.strip()
        if _name_taken(nome):
            flash("Já existe um departamento com esse nome.", "warning")
        else:
            try:
                db.session.add(Department(name=nome, is_active=bool(form.is_active.data)))
                db.session.commit()
                flash("Departamento cadastrado!", "success")
                return redirect(url_for("departments.list_view"))
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar (nome duplicado).", "danger")
    return render_template("departments/form.html", form=form, title="Novo Departamento")


@bp.route("/<int:did>/edit", methods=["GET", "POST"])
def edit(did):
    dep = Department.query.get_or_404(did)
    old_name = dep.name
    form = DepartmentForm(obj=dep)
    if form.validate_on_submit():
        nome = form.name.data.strip()
        if _name_taken(nome, ignore_id=dep.id):
            flash("Já existe um departamento com esse nome.", "warning")
        else:
            try:
                dep.name = nome
                dep.is_active = bool(form.is_active.data)
                # Renomeou o departamento? Atualiza os colaboradores que usam o
                # nome antigo, para manter o vínculo consistente.
                if nome != old_name:
                    User.query.filter(db.func.lower(User.sector) == old_name.lower())\
                        .update({"sector": nome}, synchronize_session=False)
                db.session.commit()
                flash("Departamento atualizado!", "success")
                return redirect(url_for("departments.list_view"))
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar (nome duplicado).", "danger")
    return render_template("departments/form.html", form=form, title="Editar Departamento")


@bp.route("/<int:did>/toggle-active", methods=["POST"])
def toggle_active(did):
    dep = Department.query.get_or_404(did)
    dep.is_active = not bool(dep.is_active)
    db.session.commit()
    flash(f"“{dep.name}” {'ativado' if dep.is_active else 'inativado'}.", "success")
    return redirect(url_for("departments.list_view"))


@bp.route("/<int:did>/delete", methods=["POST"])
def delete(did):
    dep = Department.query.get_or_404(did)
    em_uso = _people_counts().get(dep.name.strip().lower(), 0)
    if em_uso:
        flash(f"Não é possível excluir: {em_uso} colaborador(es) usam “{dep.name}”. "
              "Inative o departamento ou mova esses colaboradores antes.", "warning")
        return redirect(url_for("departments.list_view"))
    db.session.delete(dep)
    db.session.commit()
    flash("Departamento excluído.", "success")
    return redirect(url_for("departments.list_view"))
