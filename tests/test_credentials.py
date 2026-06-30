"""
Testes do cofre de credenciais (admin): cifragem Fernet em repouso, regra de
"senha em branco mantém a atual" na edição, endpoint de revelar e o gate de
acesso (só admin).

Marcador: credenciais criadas têm name começando com "PYTEST"; removidas no
teardown.
"""
import pytest

from inventory.extensions import db
from inventory.models.credential import Credential
from inventory.repositories import credential_repo
from inventory.services import crypto

MARK = "PYTEST"


@pytest.fixture(autouse=True)
def _cleanup_credentials(app):
    yield
    with app.app_context():
        for c in Credential.query.filter(Credential.name.like(f"{MARK}%")).all():
            db.session.delete(c)
        db.session.commit()


# --------------------------------------------------------------------------- #
# Cifragem (crypto)
# --------------------------------------------------------------------------- #
def test_encrypt_roundtrip(app):
    with app.app_context():
        token = crypto.encrypt("s3nh4-secreta")
        assert token != "s3nh4-secreta"
        assert crypto.decrypt(token) == "s3nh4-secreta"
        assert crypto.is_encrypted(token) is True


def test_decrypt_tolerates_legacy_plaintext(app):
    """Valor legado em texto puro (pré-migração) volta como está, sem quebrar."""
    with app.app_context():
        assert crypto.decrypt("texto-puro-legado") == "texto-puro-legado"
        assert crypto.is_encrypted("texto-puro-legado") is False


def test_encrypt_empty_is_noop(app):
    with app.app_context():
        assert crypto.encrypt("") == ""
        assert crypto.decrypt("") == ""


# --------------------------------------------------------------------------- #
# Repositório
# --------------------------------------------------------------------------- #
def test_create_stores_password_encrypted(app):
    with app.app_context():
        c = credential_repo.create_credential(name=f"{MARK} Servidor", category="servidor",
                                              username="root", password="p@ss")
        assert c.password != "p@ss"                 # cifrada em repouso
        assert crypto.decrypt(c.password) == "p@ss"  # decifra de volta


def test_update_blank_password_keeps_current(app):
    with app.app_context():
        c = credential_repo.create_credential(name=f"{MARK} Mantem", category="sistema",
                                              password="original")
        enc_before = c.password
        credential_repo.update_credential(c, name=f"{MARK} Mantem2", password=None)
        assert c.password == enc_before                  # inalterada
        assert crypto.decrypt(c.password) == "original"
        assert c.name == f"{MARK} Mantem2"               # outros campos mudam


def test_update_changes_password_when_provided(app):
    with app.app_context():
        c = credential_repo.create_credential(name=f"{MARK} Troca", category="sistema",
                                              password="velha")
        credential_repo.update_credential(c, password="nova")
        assert crypto.decrypt(c.password) == "nova"


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
def test_reveal_returns_plaintext(app, auth_client):
    with app.app_context():
        c = credential_repo.create_credential(name=f"{MARK} Reveal", category="email",
                                              password="visivel123")
        cid = c.id
    r = auth_client.get(f"/credentials/{cid}/reveal")
    assert r.status_code == 200
    assert r.get_json()["password"] == "visivel123"


def test_admin_creates_via_form(app, auth_client):
    r = auth_client.post("/credentials/new", data={
        "name": f"{MARK} Form", "category": "site", "username": "admin",
        "password": "formpass", "url": "https://x.example",
    }, follow_redirects=False)
    assert r.status_code in (301, 302)
    with app.app_context():
        c = Credential.query.filter_by(name=f"{MARK} Form").first()
        assert c is not None and crypto.decrypt(c.password) == "formpass"


# --------------------------------------------------------------------------- #
# Controle de acesso (só admin)
# --------------------------------------------------------------------------- #
def test_common_user_blocked(common_client):
    """Cofre é admin-only; o gate global barra o usuário comum."""
    assert common_client.get("/credentials").status_code in (302, 403)


def test_anonymous_redirected_to_login(client):
    r = client.get("/credentials", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert "/login" in r.headers.get("Location", "")
