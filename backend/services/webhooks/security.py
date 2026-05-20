"""HMAC saliente + cifrado/decifrado de secretos por suscripción."""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets

from cryptography.fernet import Fernet


def generate_secret() -> str:
    """Secreto HMAC base64 url-safe de 32 bytes (R43)."""
    return secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    key = (
        os.environ.get("MYE_WEBHOOK_FERNET_KEY")
        or os.environ.get("ENCRYPTION_KEY")
        or os.environ.get("MYE_FERNET_KEY")
    )
    if not key:
        raise RuntimeError(
            "Falta ENCRYPTION_KEY/MYE_WEBHOOK_FERNET_KEY en .env "
            "para cifrar secretos HMAC.")
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")


def sign_body(*, secret: str, body: bytes) -> str:
    """Devuelve `sha256=<hex>` (formato estándar HMAC saliente)."""
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def verify_signature(*, secret: str, body: bytes, signature: str) -> bool:
    expected = sign_body(secret=secret, body=body)
    return hmac.compare_digest(expected, signature)
