"""
Symmetric encryption helper for client integration credentials (R00A.2).

ENCRYPTION_KEY resolution order:
  1. os.environ['ENCRYPTION_KEY']
  2. config.encryption_key in MongoDB (auto-generated and persisted on first start)

Persistencia en MongoDB sobrevive a redeploys del pod (decisión del usuario).
La clave NUNCA se loguea ni se envía al frontend.
"""
import os
import json
import base64
import logging
from typing import Dict
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_FERNET_INSTANCE: Fernet | None = None


async def _resolve_encryption_key(db) -> bytes:
    """Get the encryption key. Generate+persist if missing."""
    env_key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if env_key:
        try:
            # Validate format
            Fernet(env_key.encode())
            return env_key.encode()
        except (ValueError, InvalidToken):
            logger.error("ENCRYPTION_KEY in env is not a valid Fernet key — falling back to MongoDB-stored key")

    # Try MongoDB
    doc = await db.config.find_one({"key": "encryption_key"}, {"_id": 0, "value": 1})
    if doc and doc.get("value"):
        try:
            Fernet(doc["value"].encode())
            return doc["value"].encode()
        except (ValueError, InvalidToken):
            logger.error("Stored encryption_key is invalid — generating new one (existing encrypted credentials will be unrecoverable)")

    # Generate new and persist
    key = Fernet.generate_key()
    await db.config.update_one(
        {"key": "encryption_key"},
        {"$set": {"key": "encryption_key", "value": key.decode(), "auto_generated": True}},
        upsert=True,
    )
    logger.warning(
        "[encryption] No ENCRYPTION_KEY in env — auto-generated and persisted in MongoDB. "
        "For production multi-pod setups, set ENCRYPTION_KEY env var explicitly."
    )
    return key


async def init_encryption(db) -> None:
    """Initialize the global Fernet instance. Called once at startup."""
    global _FERNET_INSTANCE
    key = await _resolve_encryption_key(db)
    _FERNET_INSTANCE = Fernet(key)
    logger.info("[encryption] Fernet initialized")


def _get_fernet() -> Fernet:
    if _FERNET_INSTANCE is None:
        raise RuntimeError("Encryption not initialized — call init_encryption(db) at startup")
    return _FERNET_INSTANCE


def encrypt_credentials(credentials: Dict) -> str:
    """Cifra un dict de credenciales -> string base64 listo para Mongo."""
    if not credentials:
        return ""
    raw = json.dumps(credentials, separators=(",", ":")).encode("utf-8")
    token = _get_fernet().encrypt(raw)
    return base64.b64encode(token).decode("ascii")


def decrypt_credentials(encrypted: str) -> Dict:
    """Descifra el string base64 de Mongo -> dict original."""
    if not encrypted:
        return {}
    try:
        token = base64.b64decode(encrypted.encode("ascii"))
        raw = _get_fernet().decrypt(token)
        return json.loads(raw.decode("utf-8"))
    except (ValueError, InvalidToken, json.JSONDecodeError) as e:
        logger.error(f"[encryption] decrypt failed: {type(e).__name__}")
        return {}


def public_credentials_summary(credentials: Dict) -> Dict:
    """Summary safe to send to frontend — booleans only, no values."""
    return {
        "has_api_key": bool(credentials.get("routal_api_key")),
        "has_webhook_secret": bool(credentials.get("routal_webhook_secret")),
        "routal_project_id": credentials.get("routal_project_id") or None,
    }
