# inventory/routes/profile.py
import io
import os
import time

import qrcode
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   current_app, request, session, send_file, abort)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import db
from ..forms.profile import ProfileForm
from ..models.user import User
from ..services import twofa

bp = Blueprint("profile", __name__)

SETUP_SECRET_KEY = "twofa_setup_secret"


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
            current_user.theme = form.theme.data if form.theme.data in ("dark", "light") else "dark"
            if form.photo.data:
                current_user.photo = _save_avatar(form.photo.data)
            if form.new_password.data:
                current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Perfil atualizado!", "success")
            return redirect(url_for("profile.edit"))
    return render_template("profile/edit.html", form=form)


# ===== Autenticação em dois fatores (2FA / TOTP) =====
@bp.route("/2fa/setup", methods=["GET"])
@login_required
def twofa_setup():
    if current_user.is_2fa_enabled:
        flash("A verificação em duas etapas já está ativa.", "info")
        return redirect(url_for("profile.edit"))
    # Gera (e guarda na sessão) um segredo provisório até o usuário confirmar o código.
    secret = session.get(SETUP_SECRET_KEY)
    if not secret:
        secret = twofa.new_secret()
        session[SETUP_SECRET_KEY] = secret
    uri = twofa.provisioning_uri(secret, current_user.email)
    return render_template("profile/twofa.html", secret=secret, uri=uri)


@bp.route("/2fa/qr.png")
@login_required
def twofa_qr():
    secret = session.get(SETUP_SECRET_KEY)
    if not secret:
        abort(404)
    uri = twofa.provisioning_uri(secret, current_user.email)
    img = qrcode.make(uri, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@bp.route("/2fa/enable", methods=["POST"])
@login_required
def twofa_enable():
    secret = session.get(SETUP_SECRET_KEY)
    code = (request.form.get("code") or "").strip()
    if not secret:
        flash("Sessão de configuração expirada. Tente novamente.", "warning")
        return redirect(url_for("profile.twofa_setup"))
    if not twofa.verify(secret, code):
        flash("Código inválido. Confira o app autenticador e tente de novo.", "danger")
        return redirect(url_for("profile.twofa_setup"))
    current_user.totp_secret = secret
    current_user.is_2fa_enabled = True
    db.session.commit()
    session.pop(SETUP_SECRET_KEY, None)
    flash("Verificação em duas etapas ativada! 🔒", "success")
    return redirect(url_for("profile.edit"))


@bp.route("/2fa/disable", methods=["POST"])
@login_required
def twofa_disable():
    # Exige a senha atual para desativar (evita desativar com sessão sequestrada).
    password = request.form.get("password") or ""
    if not current_user.check_password(password):
        flash("Senha incorreta. A verificação em duas etapas continua ativa.", "danger")
        return redirect(url_for("profile.edit"))
    current_user.is_2fa_enabled = False
    current_user.totp_secret = None
    db.session.commit()
    flash("Verificação em duas etapas desativada.", "success")
    return redirect(url_for("profile.edit"))


@bp.route("/logout-others", methods=["POST"])
@login_required
def logout_others():
    """Encerra todas as outras sessões (rotaciona o token; mantém a atual)."""
    from flask_login import login_user
    u = current_user._get_current_object()
    u.rotate_session_token()
    db.session.commit()
    session.permanent = True
    login_user(u, remember=True)  # re-emite a sessão atual com o token novo
    flash("Você saiu de todos os outros dispositivos.", "success")
    return redirect(url_for("profile.edit"))
