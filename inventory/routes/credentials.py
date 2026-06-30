# inventory/routes/credentials.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user

from ..repositories import credential_repo
from ..forms.credential import CredentialForm, CATEGORY_CHOICES
from ..services import audit, crypto
from ..services.pagination import paginate

bp = Blueprint("credentials", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _to_kwargs(form: CredentialForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        name=(form.name.data or "").strip(),
        category=form.category.data or "sistema",
        url=s(form.url.data),
        username=s(form.username.data),
        password=s(form.password.data),
        sector=s(form.sector.data),
        notes=s(form.notes.data),
    )


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    items = credential_repo.list_credentials(q or None, category or None)
    items, pag = paginate(items)
    return render_template("credentials/list.html", items=items, q=q, pag=pag,
                           category=category, categories=CATEGORY_CHOICES)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = CredentialForm()
    if form.validate_on_submit():
        c = credential_repo.create_credential(**_to_kwargs(form))
        audit.record("create", "credential", c.id, f"Criou credencial '{c.name}'")
        flash("Credencial salva!", "success")
        return redirect(url_for("credentials.list_view"))
    return render_template("credentials/form.html", form=form, title="Nova Credencial")


@bp.route("/<int:cid>/edit", methods=["GET", "POST"])
def edit(cid):
    c = credential_repo.get_credential(cid)
    form = CredentialForm(obj=c)
    if request.method == "GET":
        form.password.data = ""  # não expõe a senha; em branco = manter
    if form.validate_on_submit():
        credential_repo.update_credential(c, **_to_kwargs(form))
        audit.record("update", "credential", c.id, f"Alterou credencial '{c.name}'")
        flash("Credencial atualizada!", "success")
        return redirect(url_for("credentials.list_view"))
    return render_template("credentials/form.html", form=form, title="Editar Credencial")


@bp.route("/<int:cid>/delete", methods=["POST"])
def delete(cid):
    c = credential_repo.get_credential(cid)
    audit.record("delete", "credential", c.id, f"Excluiu credencial '{c.name}'")
    credential_repo.delete_credential(c)
    flash("Credencial excluída.", "success")
    return redirect(url_for("credentials.list_view"))


@bp.route("/<int:cid>/reveal")
def reveal(cid):
    """Retorna a senha em texto e registra na auditoria quem revelou."""
    c = credential_repo.get_credential(cid)
    audit.record("reveal", "credential", c.id, f"Revelou senha de '{c.name}'")
    return jsonify(password=crypto.decrypt(c.password))
