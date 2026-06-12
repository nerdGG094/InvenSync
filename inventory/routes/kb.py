# inventory/routes/kb.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..repositories import kb_repo
from ..forms.kb import KbForm, CATEGORY_CHOICES
from ..services import audit

bp = Blueprint("kb", __name__)


def _to_kwargs(form: KbForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        title=(form.title.data or "").strip(),
        category=form.category.data or "outro",
        problem=s(form.problem.data),
        solution=(form.solution.data or "").strip(),
        tags=s(form.tags.data),
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    items = kb_repo.list_articles(q or None, category or None)
    return render_template("kb/list.html", items=items, q=q, category=category,
                           categories=CATEGORY_CHOICES, is_admin=current_user.is_admin)


@bp.route("/<int:aid>")
@login_required
def detail(aid):
    a = kb_repo.get_article(aid)
    kb_repo.increment_views(a)
    return render_template("kb/detail.html", a=a, is_admin=current_user.is_admin)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not current_user.is_admin:
        abort(403)
    form = KbForm()
    if form.validate_on_submit():
        a = kb_repo.create_article(created_by_id=current_user.id, **_to_kwargs(form))
        audit.record("create", "kb", a.id, f"Criou artigo '{a.title}'")
        flash("Artigo publicado!", "success")
        return redirect(url_for("kb.detail", aid=a.id))
    return render_template("kb/form.html", form=form, title="Novo Artigo")


@bp.route("/<int:aid>/edit", methods=["GET", "POST"])
@login_required
def edit(aid):
    if not current_user.is_admin:
        abort(403)
    a = kb_repo.get_article(aid)
    form = KbForm(obj=a)
    if form.validate_on_submit():
        kb_repo.update_article(a, **_to_kwargs(form))
        flash("Artigo atualizado!", "success")
        return redirect(url_for("kb.detail", aid=a.id))
    return render_template("kb/form.html", form=form, title="Editar Artigo")


@bp.route("/<int:aid>/delete", methods=["POST"])
@login_required
def delete(aid):
    if not current_user.is_admin:
        abort(403)
    a = kb_repo.get_article(aid)
    audit.record("delete", "kb", a.id, f"Excluiu artigo '{a.title}'")
    kb_repo.delete_article(a)
    flash("Artigo excluído.", "success")
    return redirect(url_for("kb.list_view"))
