
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..repositories import category_repo
from ..forms.catalog import CategoryForm
from ..models.category import Category

bp = Blueprint("categories", __name__)

@bp.route("")
@login_required
def list_view():
    q = request.args.get("q","")
    items = category_repo.list_categories(q)
    return render_template("categories/list.html", items=items, q=q)

@bp.route("/new", methods=["GET","POST"])
@login_required
def new():
    form = CategoryForm()
    if form.validate_on_submit():
        try:
            category_repo.create_category(form.name.data.strip(), form.description.data)
            flash("Categoria criada!", "success"); return redirect(url_for("categories.list_view"))
        except Exception:
            flash("Erro: nome de categoria deve ser único.", "danger")
    return render_template("categories/form.html", form=form, title="Nova Categoria")

@bp.route("/<int:cid>/edit", methods=["GET","POST"])
@login_required
def edit(cid):
    c = Category.query.get_or_404(cid)
    form = CategoryForm(obj=c)
    if form.validate_on_submit():
        try:
            category_repo.update_category(c, form.name.data.strip(), form.description.data)
            flash("Categoria atualizada!", "success"); return redirect(url_for("categories.list_view"))
        except Exception:
            flash("Erro ao atualizar categoria.", "danger")
    return render_template("categories/form.html", form=form, title="Editar Categoria")

@bp.route("/<int:cid>/delete", methods=["POST"])
@login_required
def delete(cid):
    c = Category.query.get_or_404(cid)
    try:
        category_repo.delete_category(c)
        flash("Categoria excluída.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    return redirect(url_for("categories.list_view"))
