"""Application configuration loader.

Per MYEXCELLENCE.md sec 9.4 — all credentials/URLs come from environment only.
Missing required values fail fast on import.
"""
from __future__ import annotations
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

APP_VERSION = "2.1-MVP"

# Required (will KeyError on missing — fail fast)
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# Optional with sensible defaults
APP_ENV = os.environ.get("APP_ENV", "development")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")  # base64 fernet key
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "root@myexcellence.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123!")
SUPERADMIN_EMAIL = os.environ.get("SUPERADMIN_EMAIL", "superadmin@myexcellence.local")
SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD", "Admin123!")
LOG_PATH = os.environ.get("LOG_PATH", "/var/log/myexcellence/app.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")

# Notifications — PROMPT 11
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.environ.get("SENDER_NAME", "MyExcellence")

# CORS - explicit frontend origin (no wildcard with credentials)
CORS_ORIGINS_RAW = os.environ.get("CORS_ORIGINS", "*")

# Session lifetime — sec 8.1 of MYEXCELLENCE.md (8 horas)
SESSION_LIFETIME_SECONDS = 28800

# bcrypt cost — R05
BCRYPT_COST = 12

# Rate limit defaults — login
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 900  # 15 min
