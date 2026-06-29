
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..repositories import supplier_repo
from ..forms.catalog import SupplierForm
from ..models.supplier import Supplier
from ..services.pagination import paginate

bp = Blueprint("suppliers", __name__)

@bp.route("")
@login_required
def list_view():
    q = request.args.get("q","")
    items = supplier_repo.list_suppliers(q)
    items, pag = paginate(items)
    return render_template("suppliers/list.html", items=items, q=q, pag=pag)

@bp.route("/new", methods=["GET","POST"])
@login_required
def new():
    form = SupplierForm()
    if form.validate_on_submit():
        try:
            supplier_repo.create_supplier(
                name=form.name.data.strip(),
                email=form.email.data.strip() if form.email.data else None,
                phone=form.phone.data.strip() if form.phone.data else None,
                notes=form.notes.data
            )
            flash("Fornecedor criado!", "success"); return redirect(url_for("suppliers.list_view"))
        except Exception:
            flash("Erro: nome do fornecedor deve ser único.", "danger")
    return render_template("suppliers/form.html", form=form, title="Novo Fornecedor")

@bp.route("/<int:sid>/edit", methods=["GET","POST"])
@login_required
def edit(sid):
    s = Supplier.query.get_or_404(sid)
    form = SupplierForm(obj=s)
    if form.validate_on_submit():
        try:
            supplier_repo.update_supplier(
                s,
                name=form.name.data.strip(),
                email=form.email.data.strip() if form.email.data else None,
                phone=form.phone.data.strip() if form.phone.data else None,
                notes=form.notes.data
            )
            flash("Fornecedor atualizado!", "success"); return redirect(url_for("suppliers.list_view"))
        except Exception:
            flash("Erro ao atualizar fornecedor.", "danger")
    return render_template("suppliers/form.html", form=form, title="Editar Fornecedor")

@bp.route("/<int:sid>/delete", methods=["POST"])
@login_required
def delete(sid):
    s = Supplier.query.get_or_404(sid)
    try:
        supplier_repo.delete_supplier(s)
        flash("Fornecedor excluído.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    return redirect(url_for("suppliers.list_view"))
