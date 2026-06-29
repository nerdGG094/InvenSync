"""
Fixtures dos testes de fumaça.

Importante: desligamos schedulers/notificações ANTES de importar a app
(os flags são lidos no Config em tempo de import). O banco usado é o de
`DATABASE_URL`/`DB_*` do ambiente — no CI apontamos para um Postgres dedicado.
"""
import os

os.environ.setdefault("MONITORING_ENABLED", "0")
os.environ.setdefault("ALERTS_ENABLED", "0")
os.environ.setdefault("WHATSAPP_ENABLED", "0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest


def pytest_configure(config):
    """Trava de segurança: só roda contra um banco de TESTE.

    Os testes criam/alteram registros (ex.: admin de teste). Para não poluir o
    banco de produção/dev, exigimos que DATABASE_URL/DB_NAME contenham "test",
    ou que INVENSYNC_ALLOW_DB_TESTS=1 seja definido explicitamente.
    """
    url = os.environ.get("DATABASE_URL", "")
    dbname = os.environ.get("DB_NAME", "")
    looks_test = "test" in url.lower() or "test" in dbname.lower()
    if not (looks_test or os.environ.get("INVENSYNC_ALLOW_DB_TESTS") == "1"):
        pytest.exit(
            "Recusando rodar: o banco configurado nao parece ser de teste. "
            "Aponte DATABASE_URL para um banco *_test (ex.: invensync_test) ou "
            "defina INVENSYNC_ALLOW_DB_TESTS=1 para forcar.",
            returncode=2,
        )


from inventory import create_app
from inventory.extensions import db
from inventory.models.user import User

ADMIN_EMAIL = "pytest-admin@invensync.local"
ADMIN_PASS = "pytest-pass-123"


@pytest.fixture
def app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_email(app):
    """Garante um admin ativo, com login, sem 2FA e senha conhecida."""
    with app.app_context():
        u = User.query.filter_by(email=ADMIN_EMAIL).first()
        if u is None:
            u = User(name="Pytest Admin", email=ADMIN_EMAIL)
            db.session.add(u)
        u.is_admin = True
        u.can_login = True
        u.is_active = True
        u.is_2fa_enabled = False
        u.set_password(ADMIN_PASS)
        db.session.commit()
        return ADMIN_EMAIL


@pytest.fixture
def auth_client(client, admin_email):
    r = client.post("/login", data={"email": admin_email, "password": ADMIN_PASS},
                    follow_redirects=False)
    assert r.status_code in (301, 302, 303), f"login falhou: {r.status_code}"
    return client
