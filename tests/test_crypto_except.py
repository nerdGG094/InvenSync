"""Backlog DEV #10 — `except (InvalidToken, Exception)` no crypto.

A tupla nao dizia nada (Exception ja cobre InvalidToken) e engolia erro de
configuracao junto com token invalido: sem VAULT_KEY/contexto, um texto puro
voltava como se estivesse tudo certo.
"""
import pytest

def test_ida_e_volta_do_segredo(app):
    from inventory.services import crypto
    with app.app_context():
        token = crypto.encrypt("senha-secreta")
        assert token != "senha-secreta" and crypto.looks_encrypted(token)
        assert crypto.decrypt(token) == "senha-secreta"
        assert crypto.is_encrypted(token) is True


def test_texto_puro_legado_volta_como_esta(app):
    from inventory.services import crypto
    with app.app_context():
        assert crypto.decrypt("senha-antiga-em-texto") == "senha-antiga-em-texto"
        assert crypto.is_encrypted("senha-antiga-em-texto") is False


def test_token_com_chave_errada_levanta_em_vez_de_vazar_ciphertext(app):
    from inventory.services import crypto
    with app.app_context():
        token = crypto.encrypt("senha-secreta")
    with app.app_context():
        app.config["VAULT_KEY"] = "outra-chave-completamente-diferente"
        with pytest.raises(crypto.DecryptError):
            crypto.decrypt(token)
        assert crypto.is_encrypted(token) is False


def test_erro_de_configuracao_aparece_em_vez_de_virar_texto_puro(app):
    """Sem contexto de app, `_fernet()` falha. Antes isso era engolido e o
    valor voltava como se fosse texto legado — a falha só apareceria quando
    alguém tentasse usar a senha errada."""
    from inventory.services import crypto
    with pytest.raises(RuntimeError):
        crypto.decrypt("qualquer-coisa")


def test_except_do_crypto_nao_e_redundante():
    """`except (InvalidToken, Exception)` não diz nada: Exception já cobre tudo."""
    import pathlib
    fonte = pathlib.Path("inventory/services/crypto.py").read_text(encoding="utf-8")
    assert "InvalidToken, Exception" not in fonte
