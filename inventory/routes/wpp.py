# inventory/routes/wpp.py — teste/diagnóstico das notificações por e-mail, somente admin (TI)
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..services import mailer

bp = Blueprint("wpp", __name__)


@bp.before_request
def _guard():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@bp.route("")
@login_required
def page():
    return render_template(
        "wpp/test.html",
        mail_enabled=mailer._enabled(),
        mail_configured=mailer.configured(),
        mail_ti=mailer._ti_recipients(),
    )


@bp.route("/email-test", methods=["POST"])
@login_required
def email_test():
    if not mailer._enabled():
        flash("E-mail desativado: defina MAIL_ENABLED=1 no .env e reinicie.", "warning")
    elif not mailer.configured():
        flash("E-mail não configurado: preencha SMTP_HOST e MAIL_TI no .env.", "warning")
    else:
        # Envio SÍNCRONO para reportar sucesso/erro na hora.
        ok = mailer._send_raw(
            mailer._ti_recipients(),
            "[InvenSync] E-mail de teste",
            f"Teste de configuração SMTP do InvenSync.\nDisparado por {current_user.name}.",
        )
        if ok:
            flash("E-mail de teste enviado à TI. Confira a caixa de entrada.", "success")
        else:
            flash("Falha ao enviar o e-mail. Verifique host/porta/usuário/senha e o log do servidor.", "danger")
    return redirect(url_for("wpp.page"))
