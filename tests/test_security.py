"""Regressões da revisão de segurança (#3)."""
import re

import pytest

from inventory.extensions import db
from inventory.models.user import User
from inventory.models.ticket import Ticket
from inventory.repositories import ticket_repo

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        Ticket.query.filter(Ticket.title.like(f"{MARK}%")).delete()
        User.query.filter(User.name.like(f"{MARK}%")).delete()
        db.session.commit()


def test_csp_uses_nonce_and_drops_unsafe_inline(app):
    """S-CSP: script-src usa nonce por request (e NÃO 'unsafe-inline'); o nonce
    do header tem que ser o mesmo dos <script> renderizados."""
    client = app.test_client()
    r = client.get("/login")
    csp = r.headers.get("Content-Security-Policy", "")
    script_src = re.search(r"script-src[^;]*", csp)
    assert script_src, "CSP sem script-src"
    assert "'unsafe-inline'" not in script_src.group(0)
    assert "object-src 'none'" in csp

    nonce = re.search(r"'nonce-([\w-]+)'", script_src.group(0))
    assert nonce, "script-src sem nonce"
    html = r.get_data(as_text=True)
    assert set(re.findall(r'<script nonce="([\w-]+)"', html)) == {nonce.group(1)}

    # o nonce precisa ser novo a cada resposta
    r2 = client.get("/login")
    n2 = re.search(r"'nonce-([\w-]+)'", r2.headers.get("Content-Security-Policy", ""))
    assert n2 and n2.group(1) != nonce.group(1)


def test_kiox_map_has_its_own_csp(auth_client):
    """O mapa KioX é servido cru (sem Jinja), então não tem nonce: precisa do
    CSP próprio com 'unsafe-inline', senão o JS dele (e o login) não roda."""
    r = auth_client.get("/kiox")
    if r.status_code == 404:
        pytest.skip("mapa do KioX não está presente nesta instalação")
    assert r.status_code == 200
    csp = r.headers.get("Content-Security-Policy", "")
    script_src = re.search(r"script-src[^;]*", csp)
    assert script_src and "'unsafe-inline'" in script_src.group(0)
    assert "nonce-" not in csp                     # página crua não tem nonce
    assert "https://*.firebaseio.com" in csp       # Firebase (dados da frota)
    assert "nominatim.openstreetmap.org" in csp    # geocoding


def test_ticket_authz_binds_requester_by_stable_id(app):
    """S4: o solicitante é vinculado por id (não pelo nome, que é mutável).
    Assim, renomear-se no perfil não dá acesso ao chamado de outra pessoa."""
    with app.app_context():
        u = User(name=f"{MARK} Solicitante", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id

        t = ticket_repo.create_ticket(
            opened_by_id=None, title=f"{MARK} chamado", status="aberto",
            requester=f"{MARK} Solicitante")
        assert t.requester_id == uid   # vínculo estável por id

        # Solicitante em texto livre sem cadastro → sem vínculo (ninguém herda).
        t2 = ticket_repo.create_ticket(
            opened_by_id=None, title=f"{MARK} sem dono", status="aberto",
            requester="Zzz Inexistente Qwerty")
        assert t2.requester_id is None


# ---------------------------------------------------------------------------
# S-REDIR: `request.referrer` é cabeçalho do cliente. Antes, três rotas faziam
# `redirect(request.referrer or ...)` e aceitavam qualquer destino — uma página
# externa conseguia fazer o app devolver o usuário para onde ela quisesse, o
# que empresta ao golpe a credibilidade de ter partido do sistema.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ref, ok", [
    ("/tickets", True),                       # caminho do próprio site
    ("/tickets?status=aberto", True),
    (None, False),                            # sem referrer -> padrão
    ("https://falso.example/login", False),   # outro host
    ("//falso.example/login", False),         # relativo a protocolo
    (r"/\falso.example", False),             # barra invertida: o navegador normaliza para //
    ("javascript:alert(1)", False),           # esquema executável
    ("data:text/html,<script>1</script>", False),
])
def test_destino_seguro_so_aceita_o_proprio_site(app, ref, ok):
    from inventory.seguranca import destino_seguro
    with app.test_request_context("/", base_url="http://localhost"):
        assert destino_seguro(ref) == (ref if ok else None)


def test_destino_seguro_aceita_url_absoluta_do_proprio_host(app):
    from inventory.seguranca import destino_seguro
    with app.test_request_context("/", base_url="http://localhost"):
        assert destino_seguro("http://localhost/tickets") == "http://localhost/tickets"


def test_csrf_expirado_nao_redireciona_para_fora(app):
    """O handler de CSRF expirado voltava para o `Referer` sem checar o host."""
    client = app.test_client()
    r = client.post("/login", data={"email": "a@b.c", "password": "x"},
                    headers={"Referer": "https://falso.example/phish"})
    destino = r.headers.get("Location", "")
    assert "falso.example" not in destino, f"redirecionou para fora: {destino}"


def test_busca_global_nao_interpola_url_crua(app):
    """S-XSS: a url do resultado ia crua para dentro do href, no meio de irmãs
    escapadas. Segura hoje (url_for + ids inteiros), mas era armadilha."""
    fonte = (app.jinja_env.get_template("base.html").filename)
    with open(fonte, encoding="utf-8") as f:
        html = f.read()
    assert "href=\"'+it.url+'\"" not in html, "url ainda entra crua no href"
    assert "esc(it.url)" in html


# ---------------------------------------------------------------------------
# S-SEED: o admin inicial tinha a senha "admin" fixa no codigo. Em instalacao
# nova isso e uma conta de administrador com credencial publica -- e ela
# sobrevive esquecida (sobrou uma no banco de producao, sem 2FA).
# ---------------------------------------------------------------------------
def test_senha_do_admin_inicial_nao_e_fixa_no_codigo():
    import inspect
    import inventory
    src = inspect.getsource(inventory.create_app)
    i = src.find('email="admin@local"')
    assert i > 0, "nao achei o seed do admin inicial"
    # Janela dos DOIS lados: a geracao da senha vem antes da linha do e-mail.
    trecho = src[max(0, i - 500):i + 600]
    assert 'set_password("admin")' not in trecho, "senha fixa voltou ao seed"
    assert "secrets.token_urlsafe" in trecho, "o seed precisa gerar senha aleatoria"


def test_seed_respeita_senha_do_ambiente(monkeypatch):
    """Instalacao automatizada define SEED_ADMIN_PASSWORD; sem ela, aleatoria."""
    import inspect
    import inventory
    src = inspect.getsource(inventory.create_app)
    assert "SEED_ADMIN_PASSWORD" in src
