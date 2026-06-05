"""Encryption helper for sensitive credentials — Bootstrap P1.1 + R07.

Uses cryptography.Fernet (AES-128-CBC + HMAC-SHA256) as a libsodium-equivalent
free alternative for the MVP. Key lives in ``ENCRYPTION_KEY`` env var.

If ENCRYPTION_KEY is missing or invalid, startup fails. Configuration must come
from .env; no ephemeral encryption fallback is allowed.
"""
from __future__ import annotations
import base64

from cryptography.fernet import Fernet, InvalidToken

from .config import ENCRYPTION_KEY


def _resolve_key() -> bytes:
    if ENCRYPTION_KEY:
        try:
            # Accept either a urlsafe-base64 fernet key or 32 raw bytes hex
            base64.urlsafe_b64decode(ENCRYPTION_KEY.encode())
            return ENCRYPTION_KEY.encode()
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError("ENCRYPTION_KEY must be set to a valid Fernet key in .env")


_FERNET = Fernet(_resolve_key())


def encrypt(plaintext: str) -> str:
    return _FERNET.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    try:
        return _FERNET.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt: invalid token or wrong key") from exc


def generate_key() -> str:
    """Helper for ops to seed ENCRYPTION_KEY in .env."""
    return Fernet.generate_key().decode("utf-8")
