# inventory/routes/credentials.py
import os
import time

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify, current_app, send_from_directory)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import db
from ..repositories import credential_repo
from ..forms.credential import CredentialForm, CATEGORY_CHOICES
from ..models.credential_photo import CredentialPhoto
from ..services import audit, crypto, people
from ..services.pagination import paginate

bp = Blueprint("credentials", __name__)

# Só imagens — as fotos são exibidas como miniatura nos cards.
ALLOWED_PHOTO_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _save_photo(file_storage, cred):
    """Salva uma imagem na pasta privada e cria o registro. Ignora tipos não-imagem."""
    folder = current_app.config["CRED_PHOTO_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    safe = secure_filename(file_storage.filename or "foto")
    ext = (safe.rsplit(".", 1)[-1] if "." in safe else "").lower()
    if ext not in ALLOWED_PHOTO_EXT:
        return None
    fname = f"c{cred.id}_{int(time.time() * 1000)}_{safe}"
    file_storage.save(os.path.join(folder, fname))
    path = os.path.join(folder, fname)
    size = os.path.getsize(path) if os.path.exists(path) else None
    ph = CredentialPhoto(credential_id=cred.id, filename=fname, original_name=safe,
                         content_type=file_storage.mimetype, size=size)
    db.session.add(ph)
    return ph


def _handle_photo_uploads(cred):
    """Processa o campo <input name="photos" multiple> do formulário."""
    saved = rejected = 0
    for f in request.files.getlist("photos"):
        if not f or not f.filename:
            continue
        if _save_photo(f, cred):
            saved += 1
        else:
            rejected += 1
    if saved:
        db.session.commit()
        audit.record("create", "credential_photo", cred.id,
                     f"Anexou {saved} foto(s) à credencial '{cred.name}'")
        flash(f"{saved} foto(s) anexada(s).", "success")
    if rejected:
        flash(f"{rejected} arquivo(s) ignorado(s) (envie apenas imagens).", "warning")


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
    form.sector.choices = people.department_choices(form.sector.data)
    if form.validate_on_submit():
        c = credential_repo.create_credential(**_to_kwargs(form))
        audit.record("create", "credential", c.id, f"Criou credencial '{c.name}'")
        _handle_photo_uploads(c)
        flash("Credencial salva!", "success")
        return redirect(url_for("credentials.list_view"))
    return render_template("credentials/form.html", form=form, title="Nova Credencial", cred=None)


@bp.route("/<int:cid>/edit", methods=["GET", "POST"])
def edit(cid):
    c = credential_repo.get_credential(cid)
    form = CredentialForm(obj=c)
    form.sector.choices = people.department_choices(form.sector.data)  # inclui o setor atual
    if request.method == "GET":
        form.password.data = ""  # não expõe a senha; em branco = manter
    if form.validate_on_submit():
        credential_repo.update_credential(c, **_to_kwargs(form))
        audit.record("update", "credential", c.id, f"Alterou credencial '{c.name}'")
        _handle_photo_uploads(c)
        flash("Credencial atualizada!", "success")
        return redirect(url_for("credentials.edit", cid=c.id))
    return render_template("credentials/form.html", form=form, title="Editar Credencial", cred=c)


@bp.route("/<int:cid>/delete", methods=["POST"])
def delete(cid):
    c = credential_repo.get_credential(cid)
    audit.record("delete", "credential", c.id, f"Excluiu credencial '{c.name}'")
    # Remove os arquivos das fotos do disco (os registros somem via cascade).
    folder = current_app.config["CRED_PHOTO_FOLDER"]
    for ph in list(c.photos):
        try:
            p = os.path.join(folder, ph.filename)
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
    credential_repo.delete_credential(c)
    flash("Credencial excluída.", "success")
    return redirect(url_for("credentials.list_view"))


@bp.route("/<int:cid>/photo/<int:pid>")
def photo(cid, pid):
    """Serve a imagem da pasta PRIVADA — protegida pelo _only_admin do blueprint."""
    ph = CredentialPhoto.query.filter_by(id=pid, credential_id=cid).first_or_404()
    return send_from_directory(current_app.config["CRED_PHOTO_FOLDER"], ph.filename)


@bp.route("/<int:cid>/photo/<int:pid>/delete", methods=["POST"])
def photo_delete(cid, pid):
    ph = CredentialPhoto.query.filter_by(id=pid, credential_id=cid).first_or_404()
    try:
        p = os.path.join(current_app.config["CRED_PHOTO_FOLDER"], ph.filename)
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass
    db.session.delete(ph)
    db.session.commit()
    audit.record("delete", "credential_photo", cid, "Removeu foto de credencial")
    flash("Foto removida.", "success")
    return redirect(url_for("credentials.edit", cid=cid))


@bp.route("/<int:cid>/reveal")
def reveal(cid):
    """Retorna a senha em texto e registra na auditoria quem revelou."""
    c = credential_repo.get_credential(cid)
    audit.record("reveal", "credential", c.id, f"Revelou senha de '{c.name}'")
    return jsonify(password=crypto.decrypt(c.password))
