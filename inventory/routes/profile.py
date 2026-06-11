# inventory/routes/profile.py
import os
import time

from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import db
from ..forms.profile import ProfileForm
from ..models.user import User

bp = Blueprint("profile", __name__)


def _save_avatar(file_storage) -> str:
    folder = current_app.config["AVATAR_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    ext = (secure_filename(file_storage.filename).rsplit(".", 1)[-1] or "png").lower()
    fname = f"user_{current_user.id}_{int(time.time())}.{ext}"
    file_storage.save(os.path.join(folder, fname))
    # remove a foto anterior
    if current_user.photo and current_user.photo != fname:
        old = os.path.join(folder, current_user.photo)
        if os.path.exists(old):
            try:
                os.remove(old)
            except OSError:
                pass
    return fname


@bp.route("", methods=["GET", "POST"])
@login_required
def edit():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != current_user.id:
            flash("E-mail já em uso por outro usuário.", "warning")
        else:
            current_user.name = form.name.data.strip()
            current_user.email = email
            current_user.sector = (form.sector.data or "").strip() or None
            current_user.whatsapp = (form.whatsapp.data or "").strip() or None
            if form.photo.data:
                current_user.photo = _save_avatar(form.photo.data)
            if form.new_password.data:
                current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Perfil atualizado!", "success")
            return redirect(url_for("profile.edit"))
    return render_template("profile/edit.html", form=form)
