
from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user
from ..forms.auth import LoginForm, TwoFactorForm
from ..models.user import User
from ..services import twofa

bp = Blueprint("auth", __name__)

PENDING_KEY = "pending_2fa_uid"

def _home_for(user):
    """Tela inicial conforme o perfil: admin -> painel, comum -> chamados."""
    return url_for("dashboard.index") if user.is_admin else url_for("tickets.list_view")


@bp.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.can_login and user.check_password(form.password.data):
            if not user.is_active:
                flash("Usuário desativado. Procure um administrador.", "warning")
                return render_template("login.html", form=form)
            # Senha OK. Se o usuário tem 2FA ativo, exige o segundo fator antes de logar.
            if user.is_2fa_enabled and user.totp_secret:
                session[PENDING_KEY] = user.id
                return redirect(url_for("auth.login_2fa"))
            login_user(user)
            return redirect(_home_for(user))
        flash("Credenciais inválidas", "danger")
    return render_template("login.html", form=form)


@bp.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    uid = session.get(PENDING_KEY)
    if not uid:
        return redirect(url_for("auth.login"))
    user = User.query.get(uid)
    if not user or not user.is_active or not user.is_2fa_enabled or not user.totp_secret:
        session.pop(PENDING_KEY, None)
        return redirect(url_for("auth.login"))

    form = TwoFactorForm()
    if form.validate_on_submit():
        if twofa.verify(user.totp_secret, form.code.data):
            session.pop(PENDING_KEY, None)
            login_user(user)
            return redirect(_home_for(user))
        flash("Código inválido. Tente novamente.", "danger")
    return render_template("login_2fa.html", form=form)


@bp.route("/login/cancel")
def login_cancel():
    """Cancela uma verificação 2FA pendente e volta ao login."""
    session.pop(PENDING_KEY, None)
    return redirect(url_for("auth.login"))


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
