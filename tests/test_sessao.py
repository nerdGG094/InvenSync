"""Por que a sessao caiu — o motivo tem que ficar registrado.

O sintoma relatado foi "navegando normalmente, volta para a tela de login,
sem mensagem". Sem mensagem porque login_message = None; e sem rastro porque o
user_loader engolia tudo num `except Exception: return None`. Estes testes
garantem que cada motivo deixe registro.
"""
from inventory.extensions import db
from inventory.models.error_log import ErrorLog
from inventory.models.user import User


def _ultimo(app, source):
    with app.app_context():
        return (ErrorLog.query.filter_by(source=source)
                .order_by(ErrorLog.id.desc()).first())


def test_token_trocado_deixa_registro(app):
    """'Sair de todas as sessoes' invalida o cookie — e isso tem que aparecer."""
    with app.app_context():
        u = User.query.filter_by(can_login=True).first()
        assert u is not None
        uid, token = u.id, (u.session_token or "")
    if not token:
        return  # instalacao sem token: a checagem nao se aplica

    with app.test_request_context("/"):
        from flask_login import login_manager as _lm  # noqa: F401
        carregar = app.login_manager._user_callback
        assert carregar(f"{uid}:token-que-nao-confere") is None

    reg = _ultimo(app, "user_loader")
    assert reg is not None, "token invalido nao deixou rastro"
    assert "token de sess" in (reg.message or "")


def test_usuario_inexistente_deixa_registro(app):
    with app.test_request_context("/"):
        carregar = app.login_manager._user_callback
        assert carregar("99999999:qualquer") is None
    reg = _ultimo(app, "user_loader")
    assert reg and "inexistente" in (reg.message or "")


def test_redirecionado_ao_login_com_cookie_gera_registro(app):
    """Quem tinha cookie e mesmo assim caiu no login: e o caso a investigar."""
    c = app.test_client()
    c.set_cookie("session", "cookie-invalido-qualquer")
    r = c.get("/products")
    assert r.status_code == 302 and "/login" in r.headers.get("Location", "")
    reg = _ultimo(app, "sessao_perdida")
    assert reg is not None, "queda com cookie presente precisa ficar registrada"
    assert "presente" in (reg.message or "")


def test_visita_anonima_nao_polui_o_log(app):
    """Sem cookie nenhum e navegacao normal de quem nao logou — nao e incidente."""
    antes = _ultimo(app, "sessao_perdida")
    antes_id = antes.id if antes else 0
    r = app.test_client().get("/products")
    assert r.status_code == 302
    depois = _ultimo(app, "sessao_perdida")
    assert (depois.id if depois else 0) == antes_id, "visita anonima virou ruido no log"
