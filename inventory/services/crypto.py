"""
Cifragem simétrica para segredos em repouso (cofre de senhas).

A chave Fernet é derivada de `VAULT_KEY` (se definida no .env) ou, na falta,
do `SECRET_KEY`. **Importante:** se a chave mudar, os segredos já cifrados não
poderão ser decifrados — defina um `VAULT_KEY` fixo no .env para produção.

`decrypt()` é tolerante: valores legados em texto puro (ainda não migrados)
são retornados como estão.
"""
import base64
import hashlib

from flask import current_app
from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = (current_app.config.get("VAULT_KEY")
           or current_app.config.get("SECRET_KEY")
           or "dev-secret-key")
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plain):
    if not plain:
        return plain
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def is_encrypted(token) -> bool:
    if not token:
        return False
    try:
        _fernet().decrypt(token.encode("utf-8"))
        return True
    except (InvalidToken, Exception):  # noqa: BLE001
        return False


def decrypt(token):
    if not token:
        return token or ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):  # noqa: BLE001
        # valor legado em texto puro (pré-migração) — devolve como está
        return token
