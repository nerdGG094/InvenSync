"""
Testes de fumaça: garantem que a app sobe, as rotas principais respondem e as
proteções básicas (login obrigatório, rate limit) funcionam. Não validam regras
de negócio — são uma rede de segurança contra quebras grosseiras.
"""
import pytest


def test_app_boots(app):
    assert app is not None


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200


def test_protected_redirects_anonymous(client):
    r = client.get("/products", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert "/login" in r.headers.get("Location", "")


# Páginas-chave que um admin deve conseguir abrir (200).
ADMIN_PAGES = [
    "/",                      # dashboard
    "/products",
    "/movements",
    "/categories",
    "/suppliers",
    "/machines",
    "/machines/mobile",
    "/machines/maintenance",
    "/machines/cleanings",
    "/machines/monitoring",
    "/tickets",
    "/avisos",
    "/credentials",
    "/audit",
    "/departments",
    "/licenses",
    "/domains",
    "/colaboradores",
]


@pytest.mark.parametrize("url", ADMIN_PAGES)
def test_admin_pages_load(auth_client, url):
    r = auth_client.get(url, follow_redirects=False)
    assert r.status_code == 200, f"{url} -> {r.status_code}"


def test_login_rate_limited(client):
    """Após o limite (10/min) o handler 429 redireciona (302)."""
    codes = [
        client.post("/login", data={"email": "x@x", "password": "y"},
                    follow_redirects=False).status_code
        for _ in range(13)
    ]
    assert 302 in codes, f"rate limit não disparou: {codes}"


def test_alerts_publish(app):
    """O serviço de alertas roda e cria/atualiza o aviso automático."""
    from inventory.services import alerts
    total = alerts.publish(app)
    assert total >= 0
