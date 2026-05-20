"""HMAC SHA-256 signature helpers — used by /api/guias/ingest/webhook (R06).

Constant-time comparison to avoid timing attacks.
"""
from __future__ import annotations
import hashlib
import hmac as _hmac


def sign(secret: str, body: bytes) -> str:
    """Returns the hex digest used for the ``X-MyE-Signature`` header."""
    return _hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, candidate: str) -> bool:
    if not candidate:
        return False
    # Allow callers to send ``sha256=<hex>`` or just the hex digest.
    if candidate.startswith("sha256="):
        candidate = candidate[7:]
    expected = sign(secret, body)
    try:
        return _hmac.compare_digest(expected, candidate)
    except (TypeError, ValueError):
        return False
