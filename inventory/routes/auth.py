
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from ..forms.auth import LoginForm
from ..models.user import User

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        print("[LOGIN] POST received")
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("dashboard.index"))
        flash("Credenciais inválidas", "danger")
    return render_template("login.html", form=form)

@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
