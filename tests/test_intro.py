"""Página de apresentação: acesso, primeira entrada e não-regressão do menu."""


def test_abre_para_admin(app, auth_client):
    r = auth_client.get("/apresentacao")
    assert r.status_code == 200
    corpo = r.get_data(as_text=True)
    assert 'id="introCena"' in corpo            # canvas da cena 3D
    assert "css/intro.css" in corpo and "js/intro.js" in corpo


def test_abre_para_usuario_comum(app, common_client):
    """Usuário comum precisa passar pelo portão de acesso (NON_ADMIN_PREFIXES)."""
    r = common_client.get("/apresentacao")
    assert r.status_code == 200, "usuário comum foi bloqueado na apresentação"


def test_exige_login(app, client):
    r = client.get("/apresentacao")
    assert r.status_code in (301, 302) and "/login" in r.headers.get("Location", "")


def test_primeira_entrada_leva_para_a_apresentacao(app, admin_email, admin_password):
    """Quem nunca viu cai na apresentação ao logar; depois, não mais."""
    from inventory.extensions import db
    from inventory.models.user import User

    with app.app_context():
        u = User.query.filter_by(email=admin_email).first()
        u.intro_visto = False
        db.session.commit()

    c = app.test_client()
    r = c.post("/login", data={"email": admin_email, "password": admin_password})
    assert "/apresentacao" in r.headers.get("Location", ""), "não levou à apresentação"

    # Abrir a página marca como vista...
    assert c.get("/apresentacao").status_code == 200
    with app.app_context():
        assert User.query.filter_by(email=admin_email).first().intro_visto is True

    # ...e o próximo login volta ao destino normal.
    c2 = app.test_client()
    r2 = c2.post("/login", data={"email": admin_email, "password": admin_password})
    assert "/apresentacao" not in r2.headers.get("Location", "")


def test_item_fica_acima_do_painel(app, auth_client):
    corpo = auth_client.get("/apresentacao").get_data(as_text=True)
    assert corpo.index("bi-stars") < corpo.index("bi-speedometer2")


def test_estilo_nao_vaza_para_o_resto_do_app(app, client):
    """O CSS usa nomes genéricos (.card, .btn): tudo precisa ficar preso à
    apresentação, senão quebra o Bootstrap nas outras telas.

    Duas formas são aceitas: começar com `.intro`, ou ser condicionado por
    `:has(.intro)` — usado para soltar a página do `main.container`, que só
    pode valer onde a apresentação está presente."""
    import re
    css = client.get("/static/css/intro.css").get_data(as_text=True)
    sem_comentario = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    regras = [r.strip() for r in re.findall(r"([^{}]+)\{", sem_comentario) if r.strip()]
    fora = [r for r in regras
            if not r.startswith((".intro", "@")) and ":has(.intro)" not in r]
    assert fora == [], f"seletores que vazam para o resto do app: {fora}"


def test_fundo_de_bolhas_em_todas_as_telas(app, auth_client):
    """O fundo vem do base.html, então vale para tudo — e só UMA cena por tela.

    Duas cenas na mesma página seriam dois laços de render disputando a GPU."""
    # Cliente novo: o `auth_client` já está logado e /login o redirigiria.
    anonimo = app.test_client()
    corpo = anonimo.get("/login").get_data(as_text=True)
    assert 'id="fundoBolhas"' in corpo and "js/bolhas.js" in corpo
    # o degradê original continua como reserva se o 3D não carregar
    assert 'class="auth-bg"' in corpo

    for url in ("/", "/avisos", "/tickets", "/machines", "/cftv"):
        c = auth_client.get(url).get_data(as_text=True)
        assert c.count('id="fundoBolhas"') == 1, f"{url} sem o fundo (ou repetido)"

    # A apresentação tem cena própria e anula o fundo padrão.
    intro = auth_client.get("/apresentacao").get_data(as_text=True)
    assert 'id="fundoBolhas"' not in intro, "apresentação abriria duas cenas"
    assert intro.count('id="introCena"') == 1

    assert anonimo.get("/static/js/bolhas.js").status_code == 200


def test_fundo_pode_ser_desligado(app, auth_client):
    """Interruptor de emergência: máquina fraca não pode ficar refém do efeito."""
    app.config["UI_FUNDO_BOLHAS"] = False
    try:
        assert 'id="fundoBolhas"' not in auth_client.get("/").get_data(as_text=True)
    finally:
        app.config["UI_FUNDO_BOLHAS"] = True


def test_script_do_login_carrega_o_nonce_do_csp(app, client):
    """Script inline sem o nonce é bloqueado pelo CSP e o fundo não aparece."""
    import re
    r = client.get("/login")
    nonce_html = re.search(r'type="module" nonce="([^"]+)"', r.get_data(as_text=True))
    assert nonce_html, "o script do fundo está sem nonce"
    csp = r.headers.get("Content-Security-Policy", "")
    assert f"'nonce-{nonce_html.group(1)}'" in csp


def test_paginas_existentes_continuam_de_pe(app, auth_client):
    """A apresentação não pode ter mexido no resto (menu novo em toda tela)."""
    for url in ("/", "/avisos", "/tickets", "/products", "/machines"):
        assert auth_client.get(url).status_code == 200, f"{url} quebrou"
