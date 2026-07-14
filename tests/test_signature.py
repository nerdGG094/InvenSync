"""Assinatura do Termo de ativos: salva por nome e reaparece ao reabrir."""
import pytest

from inventory.extensions import db
from inventory.models.user import User
from inventory.models.machine import Machine
from inventory.models.asset_signature import AssetSignature
from inventory.models.asset_termo import AssetTermo
from inventory.routes.assets import TI_KEY

MARK = "PYTEST"
# PNG 1x1 válido como data URL de assinatura.
SIG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0"
       "lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@pytest.fixture(autouse=True)
def _cleanup(app):
    yield
    with app.app_context():
        for m in Machine.query.filter(Machine.model.like(f"{MARK}%")).all():
            db.session.delete(m)
        for u in User.query.filter(User.name.like(f"{MARK}%")).all():
            db.session.delete(u)
        AssetSignature.query.filter(AssetSignature.person_name.like(f"{MARK}%")).delete()
        AssetTermo.query.filter(AssetTermo.person_name.like(f"{MARK}%")).delete()
        db.session.commit()


def test_signature_save_and_reload(app, auth_client):
    nome = f"{MARK}Assinante"
    with app.app_context():
        db.session.add(User(name=nome, is_active=True))
        db.session.add(Machine(model=f"{MARK}-pc", assigned_user=nome))
        db.session.commit()

    # salva a assinatura
    r = auth_client.post(f"/assets/{nome}/signature", data={"signature": SIG})
    assert r.status_code == 200 and r.get_json().get("ok")
    with app.app_context():
        assert AssetSignature.query.filter_by(person_name=nome).first() is not None

    # reabrir o termo já traz a assinatura embutida no HTML
    r = auth_client.get(f"/assets/{nome}/termo")
    assert r.status_code == 200 and b"iVBOR" in r.data

    # comprovante de entrega registrado + visível no histórico
    with app.app_context():
        assert AssetTermo.query.filter_by(person_name=nome).count() == 1
    r = auth_client.get(f"/assets/{nome}/termos")
    assert r.status_code == 200 and f"{MARK}-pc".encode() in r.data

    # salvar de novo sem mudar nada NÃO duplica o comprovante
    auth_client.post(f"/assets/{nome}/signature", data={"signature": SIG})
    with app.app_context():
        assert AssetTermo.query.filter_by(person_name=nome).count() == 1


def test_rename_rekeys_signature_and_termo(app, auth_client):
    """Renomear a pessoa leva a assinatura e o comprovante para a nova chave."""
    from inventory.services import people
    nome, novo = f"{MARK}Renome", f"{MARK}Renomeado"
    with app.app_context():
        db.session.add(Machine(model=f"{MARK}-pc3", assigned_user=nome))
        db.session.commit()
    auth_client.post(f"/assets/{nome}/signature", data={"signature": SIG})
    with app.app_context():
        assert AssetSignature.query.filter_by(person_key=nome.lower()).first() is not None
        assert AssetTermo.query.filter_by(person_key=nome.lower()).count() >= 1
        people.propagate_person_rename(nome, novo)
        db.session.commit()
        # chave antiga esvaziada, nova preenchida
        assert AssetSignature.query.filter_by(person_key=nome.lower()).first() is None
        assert AssetSignature.query.filter_by(person_key=novo.lower()).first() is not None
        assert AssetTermo.query.filter_by(person_key=novo.lower()).count() >= 1


def test_decrypt_rejects_corrupt_token(app):
    """Token com estrutura Fernet que não decifra (chave errada) levanta erro em
    vez de devolver o ciphertext como se fosse a senha."""
    import pytest as _pt
    from inventory.services import crypto
    with app.app_context():
        assert crypto.decrypt(crypto.encrypt("segredo")) == "segredo"
        assert crypto.decrypt("texto-legado") == "texto-legado"   # legado passa
        with _pt.raises(crypto.DecryptError):
            crypto.decrypt("gAAAAA" + "A" * 60)


def test_ti_signature_shared(app, auth_client):
    r = auth_client.post("/assets/ti-signature", data={"signature": SIG})
    assert r.status_code == 200 and r.get_json().get("ok")
    with app.app_context():
        sig = AssetSignature.query.filter_by(person_key=TI_KEY).first()
        assert sig is not None and sig.data_url == SIG
        db.session.delete(sig)
        db.session.commit()


def test_signature_rejects_non_image(app, auth_client):
    nome = f"{MARK}Ruim"
    with app.app_context():
        db.session.add(Machine(model=f"{MARK}-pc2", assigned_user=nome))
        db.session.commit()
    r = auth_client.post(f"/assets/{nome}/signature", data={"signature": "não é imagem"})
    assert r.status_code == 400
