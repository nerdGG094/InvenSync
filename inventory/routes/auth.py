
from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, current_user
from ..forms.auth import LoginForm, TwoFactorForm
from ..models.user import User
from ..services import twofa, audit
from ..extensions import limiter, db

bp = Blueprint("auth", __name__)

PENDING_KEY = "pending_2fa_uid"

def _home_for(user):
    """Tela inicial conforme o perfil: admin -> painel, comum -> central de avisos."""
    return url_for("dashboard.index") if user.is_admin else url_for("announcements.list_view")


@bp.route("/login", methods=["GET","POST"])
@limiter.limit("10 per minute; 40 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        # Conta bloqueada por tentativas? barra antes de checar a senha.
        if user and user.is_locked():
            mins = max(1, round(user.lock_seconds_left() / 60))
            audit.record("login_fail", "user", user.id, f"Login bloqueado (conta travada) — {email}")
            flash(f"Conta temporariamente bloqueada por excesso de tentativas. Tente em ~{mins} min.", "warning")
            return render_template("login.html", form=form)

        if user and user.can_login and user.check_password(form.password.data):
            if not user.is_active:
                flash("Usuário desativado. Procure um administrador.", "warning")
                return render_template("login.html", form=form)
            # Senha OK: zera contador de falhas.
            if user.failed_logins or user.locked_until:
                user.failed_logins = 0
                user.locked_until = None
                db.session.commit()
            # Se o usuário tem 2FA ativo, exige o segundo fator antes de logar.
            if user.is_2fa_enabled and user.totp_secret:
                session[PENDING_KEY] = user.id
                return redirect(url_for("auth.login_2fa"))
            session.permanent = True
            login_user(user, remember=True)
            audit.record("login", "user", user.id, f"Login de {user.name}")
            return redirect(_home_for(user))

        # Falha de credencial: conta tentativa e bloqueia ao atingir o limite.
        if user:
            maxn = int(current_app.config.get("LOGIN_MAX_ATTEMPTS", 5) or 5)
            lockmin = int(current_app.config.get("LOGIN_LOCKOUT_MINUTES", 15) or 15)
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= maxn:
                user.locked_until = datetime.now() + timedelta(minutes=lockmin)
                user.failed_logins = 0
                audit.record("login_fail", "user", user.id,
                             f"Conta bloqueada por {lockmin} min após {maxn} tentativas — {email}")
            else:
                audit.record("login_fail", "user", user.id,
                             f"Senha incorreta ({user.failed_logins}/{maxn}) — {email}")
            db.session.commit()
        else:
            audit.record("login_fail", None, None, f"Tentativa para e-mail inexistente: {email}")
        flash("Credenciais inválidas", "danger")
    return render_template("login.html", form=form)


@bp.route("/login/2fa", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
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
            session.permanent = True
            login_user(user, remember=True)
            audit.record("login", "user", user.id, f"Login de {user.name} (2FA)")
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
