"""Application configuration loader.

Per MYEXCELLENCE.md sec 9.4 — all credentials/URLs come from environment only.
Missing required values fail fast on import.
"""
from __future__ import annotations
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

APP_VERSION = "2.1-MVP"

def _env(name: str) -> str:
    try:
        return os.environ[name]
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {name}") from exc


def _int_env(name: str) -> int:
    return int(_env(name))


# All configuration must come from .env / process env. No code fallbacks.
APP_ENV = _env("APP_ENV")

MONGO_URL = _env("MONGO_URL")
DB_NAME = _env("DB_NAME")

JWT_SECRET = _env("JWT_SECRET")
ENCRYPTION_KEY = _env("ENCRYPTION_KEY")  # base64 fernet key

ADMIN_EMAIL = _env("ADMIN_EMAIL")
ADMIN_PASSWORD = _env("ADMIN_PASSWORD")
SUPERADMIN_EMAIL = _env("SUPERADMIN_EMAIL")
SUPERADMIN_PASSWORD = _env("SUPERADMIN_PASSWORD")

LOG_PATH = _env("LOG_PATH")
LOG_LEVEL = _env("LOG_LEVEL")

RESEND_API_KEY = _env("RESEND_API_KEY")
SENDER_EMAIL = _env("SENDER_EMAIL")
SENDER_NAME = _env("SENDER_NAME")

CORS_ORIGINS_RAW = _env("CORS_ORIGINS")
EVIDENCE_ROOT = _env("EVIDENCE_ROOT")

SESSION_LIFETIME_SECONDS = _int_env("SESSION_LIFETIME_SECONDS")
BCRYPT_COST = _int_env("BCRYPT_COST")
LOGIN_MAX_ATTEMPTS = _int_env("LOGIN_MAX_ATTEMPTS")
LOGIN_LOCKOUT_SECONDS = _int_env("LOGIN_LOCKOUT_SECONDS")
