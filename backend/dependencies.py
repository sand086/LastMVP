"""
Shared dependencies for LastMile OS API.
Database connection, auth helpers, utility functions.
"""
import os
import re as re_mod
import uuid
import logging
import bcrypt
import jwt
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from starlette.requests import Request
from motor.motor_asyncio import AsyncIOMotorClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ==================== DATABASE ====================

mongo_url = os.environ['MONGO_URL']
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ['DB_NAME']]

# ==================== JWT CONFIG ====================

JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required. Set it in backend/.env")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "8"))

# ==================== RATE LIMITER ====================

limiter = Limiter(key_func=get_remote_address)

# ==================== FILE UPLOAD CONFIG ====================

UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_UPLOAD_TYPES = [
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",
]
ALLOWED_UPLOAD_EXTENSIONS = [".csv", ".xlsx", ".xls"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# ==================== SECURITY ====================

security = HTTPBearer(auto_error=False)

COOKIE_NAME = "lm_access_token"
COOKIE_MAX_AGE = JWT_EXPIRY_HOURS * 3600
COOKIE_SECURE = os.environ.get("ENVIRONMENT", "production") != "development"
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax")
COOKIE_PATH = "/api"

# ==================== AUTH HELPERS ====================

import asyncio
from concurrent.futures import ThreadPoolExecutor

_bcrypt_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bcrypt")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=11)).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

async def verify_password_async(plain: str, hashed: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _bcrypt_executor,
        lambda: bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    )

async def hash_password_async(plain: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _bcrypt_executor,
        lambda: bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt(rounds=11)).decode('utf-8')
    )

def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, email: str, role: str, days: int = 90) -> dict:
    """Create a long-lived refresh token for API/Power BI integrations."""
    jti = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "jti": jti,
        "type": "refresh",
        "exp": expires_at,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token, "jti": jti, "expires_at": expires_at.isoformat()}

async def get_current_user(request: Request):
    """Extract JWT from httpOnly cookie first, fallback to Authorization Bearer header."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        jti = payload.get("jti")
        if jti:
            revoked = await db.revoked_tokens.find_one({"jti": jti})
            if revoked:
                raise HTTPException(status_code=401, detail="Token revocado")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def require_role(allowed_roles: List[str]):
    async def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Acceso denegado")
        return user
    return role_checker

def apply_assignment_filter(user: dict, query: dict) -> dict:
    """Filter queries by user's assigned clients/providers. Empty = see all."""
    assigned_clients = user.get("assigned_clients", [])
    assigned_providers = user.get("assigned_providers", [])
    if assigned_clients:
        query["client_id"] = {"$in": assigned_clients}
    if assigned_providers:
        if "provider_id" in query:
            existing = query["provider_id"]
            if isinstance(existing, str):
                if existing in assigned_providers:
                    query["provider_id"] = existing
                else:
                    query["provider_id"] = {"$in": []}
            elif isinstance(existing, dict) and "$in" in existing:
                query["provider_id"] = {"$in": [p for p in existing["$in"] if p in assigned_providers]}
        else:
            query["provider_id"] = {"$in": assigned_providers}
    return query

# ==================== UTILITY FUNCTIONS ====================

def _next_day(date_str: str) -> str:
    """Given a date string 'YYYY-MM-DD', return the next day string."""
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return (dt + timedelta(days=1)).strftime("%Y-%m-%d")

_MEXICAN_STATES = [
    "Ciudad de México", "CDMX", "Estado de México", "Edo. Méx", "Edomex",
    "Jalisco", "Nuevo León", "Puebla", "Querétaro", "Guanajuato",
    "Aguascalientes", "Baja California", "Chihuahua", "Coahuila",
    "Colima", "Durango", "Guerrero", "Hidalgo", "Michoacán",
    "Morelos", "Nayarit", "Oaxaca", "San Luis Potosí", "Sinaloa",
    "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz",
    "Yucatán", "Zacatecas", "Campeche", "Chiapas", "Quintana Roo",
]

_RE_CP = re_mod.compile(r'\b(\d{5})\b')
_RE_COLONIA = re_mod.compile(r'(?:Col\.?|Colonia)\s+([^,\d]+)', re_mod.IGNORECASE)
_RE_MUNICIPIO = re_mod.compile(r'(?:Mun\.?|Municipio|Del\.?|Delegación|Alcaldía)\s+([^,\d]+)', re_mod.IGNORECASE)


def _extract_cp(addr: str) -> str | None:
    m = _RE_CP.search(addr)
    return m.group(1) if m else None


def _extract_state(addr_lower: str) -> str | None:
    for state in _MEXICAN_STATES:
        if state.lower() in addr_lower:
            return state
    return None


def _extract_colonia_municipio(addr: str) -> tuple:
    colonia = None
    municipio = None
    col_m = _RE_COLONIA.search(addr)
    if col_m:
        colonia = col_m.group(1).strip().rstrip(',')
    mun_m = _RE_MUNICIPIO.search(addr)
    if mun_m:
        municipio = mun_m.group(1).strip().rstrip(',')

    # Fallback: infer from comma-separated parts
    if colonia is None or municipio is None:
        parts = [p.strip() for p in addr.split(',') if p.strip()]
        if len(parts) >= 3:
            if colonia is None:
                colonia = parts[-3] if len(parts) >= 4 else parts[-2]
            if municipio is None:
                municipio = parts[-2]

    return colonia, municipio


def _normalize_address(address: str) -> dict:
    """Parse a Mexican address string to extract structured components."""
    if not address:
        return {}
    addr = address.strip()
    result = {}

    cp = _extract_cp(addr)
    if cp:
        result["address_cp"] = cp

    state = _extract_state(addr.lower())
    if state:
        result["address_estado"] = state

    colonia, municipio = _extract_colonia_municipio(addr)
    if colonia:
        result["address_colonia"] = colonia
    if municipio:
        result["address_municipio"] = municipio

    return result

def _validate_upload_file(file):
    """Validate uploaded file type, extension, and size."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no permitido. Solo CSV y XLSX.")
    ct = (file.content_type or "").lower()
    if ct and ct not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail=f"Tipo de archivo no permitido: {ct}")
