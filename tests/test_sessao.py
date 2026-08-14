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
    msg = reg.message or ""
    # O registro tem que dizer POR QUE, nao so que caiu: aqui o cookie e
    # invalido de proposito, entao o veredito da assinatura precisa aparecer.
    assert "ASSINATURA FALHOU" in msg, msg
    assert "chaves na sessao: VAZIA" in msg, msg


def test_visita_anonima_nao_polui_o_log(app):
    """Sem cookie nenhum e navegacao normal de quem nao logou — nao e incidente."""
    antes = _ultimo(app, "sessao_perdida")
    antes_id = antes.id if antes else 0
    r = app.test_client().get("/products")
    assert r.status_code == 302
    depois = _ultimo(app, "sessao_perdida")
    assert (depois.id if depois else 0) == antes_id, "visita anonima virou ruido no log"


# ---------------------------------------------------------------------------
# S-COOKIE: cookie e isolado por DOMINIO, nunca por porta. Este servidor roda
# CarregLogi na :80 e a AS na :5000, ambos Flask. Com o nome padrao os tres
# gravavam `session`/`remember_token` no mesmo dominio com Path=/ -- o MESMO
# cookie -- e quem respondesse por ultimo sobrescrevia os outros. O InvenSync
# recebia de volta cookie assinado com a chave do vizinho, a assinatura
# falhava e o usuario caia no login sem mensagem.
# ---------------------------------------------------------------------------
def test_cookies_tem_nome_proprio(app):
    assert app.config["SESSION_COOKIE_NAME"] != "session", \
        "nome padrao volta a colidir com os outros Flask do mesmo host"
    assert app.config["REMEMBER_COOKIE_NAME"] != "remember_token", \
        "o remember do Flask-Login colide igual ao da sessao"
    assert "invensync" in app.config["SESSION_COOKIE_NAME"]
    assert "invensync" in app.config["REMEMBER_COOKIE_NAME"]


def test_login_emite_os_cookies_renomeados(app):
    """Prova de ponta a ponta: o Set-Cookie sai com o nome novo."""
    from inventory.extensions import db
    from inventory.models.user import User
    app.config["WTF_CSRF_ENABLED"] = False
    email = "cookie@teste.local"
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(name="PYTEST Cookie", email=email, can_login=True,
                     is_admin=False, is_active=True)
            u.set_password("senha-de-teste-123")
            db.session.add(u)
            db.session.commit()
    r = app.test_client().post("/login", data={"email": email,
                                               "password": "senha-de-teste-123"})
    emitidos = [h.split("=")[0] for h in r.headers.getlist("Set-Cookie")]
    assert app.config["SESSION_COOKIE_NAME"] in emitidos, emitidos
    assert "session" not in emitidos, "ainda gravando no cookie compartilhado"
