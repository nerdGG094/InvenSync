# inventory/routes/wpp.py — teste/diagnóstico das notificações WhatsApp (CallMeBot), somente admin (TI)
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..services import whatsapp

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
        enabled=whatsapp._enabled(),
        configured=whatsapp.configured(),
        recipients=whatsapp._recipients(),
    )


@bp.route("/test", methods=["POST"])
@login_required
def test():
    if not whatsapp._enabled():
        flash("WhatsApp desativado: defina WHATSAPP_ENABLED=1 no .env e reinicie.", "warning")
    elif not whatsapp.configured():
        flash("Nenhum destino configurado: preencha CALLMEBOT_RECIPIENTS no .env.", "warning")
    else:
        whatsapp.notify_ti(
            f"✅ *Teste InvenSync* — notificações via CallMeBot funcionando.\n"
            f"Disparado por {current_user.name}."
        )
        flash("Mensagem de teste enviada à TI. Confira o WhatsApp.", "success")
    return redirect(url_for("wpp.page"))
