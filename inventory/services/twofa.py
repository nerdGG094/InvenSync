"""
Autenticação em dois fatores (2FA) baseada em TOTP — compatível com
Google Authenticator, Microsoft Authenticator, Authy, etc.

Fluxo:
  1. new_secret() gera um segredo base32 para o usuário.
  2. provisioning_uri() devolve a URI otpauth:// usada para montar o QR Code.
  3. verify() confere o código de 6 dígitos digitado pelo usuário.
"""
import pyotp

ISSUER = "InvenSync"


def new_secret() -> str:
    """Segredo base32 aleatório para vincular o app autenticador."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    """URI otpauth:// para gerar o QR Code no app autenticador."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=account or "usuario", issuer_name=ISSUER)


def verify(secret: str, code: str) -> bool:
    """Valida o código TOTP. valid_window=1 tolera ~30s de defasagem de relógio."""
    if not secret or not code:
        return False
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:  # noqa: BLE001
        return False
