
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from ..forms.auth import LoginForm
from ..models.user import User

bp = Blueprint("auth", __name__)

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
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("Usuário desativado. Procure um administrador.", "warning")
                return render_template("login.html", form=form)
            login_user(user)
            return redirect(_home_for(user))
        flash("Credenciais inválidas", "danger")
    return render_template("login.html", form=form)

@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
