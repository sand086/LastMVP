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
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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

JWT_SECRET = os.environ.get('JWT_SECRET', 'lastmile-os-secret-key-2026-production-v1')
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8

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

security = HTTPBearer()

# ==================== AUTH HELPERS ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
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

def _normalize_address(address: str) -> dict:
    """Parse a Mexican address string to extract structured components."""
    if not address:
        return {}
    result = {}
    addr = address.strip()

    cp_match = re_mod.search(r'\b(\d{5})\b', addr)
    if cp_match:
        result["address_cp"] = cp_match.group(1)

    states = [
        "Ciudad de México", "CDMX", "Estado de México", "Edo. Méx", "Edomex",
        "Jalisco", "Nuevo León", "Puebla", "Querétaro", "Guanajuato",
        "Aguascalientes", "Baja California", "Chihuahua", "Coahuila",
        "Colima", "Durango", "Guerrero", "Hidalgo", "Michoacán",
        "Morelos", "Nayarit", "Oaxaca", "San Luis Potosí", "Sinaloa",
        "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz",
        "Yucatán", "Zacatecas", "Campeche", "Chiapas", "Quintana Roo",
    ]
    addr_lower = addr.lower()
    for state in states:
        if state.lower() in addr_lower:
            result["address_estado"] = state
            break

    col_match = re_mod.search(r'(?:Col\.?|Colonia)\s+([^,\d]+)', addr, re_mod.IGNORECASE)
    if col_match:
        result["address_colonia"] = col_match.group(1).strip().rstrip(',')

    mun_match = re_mod.search(
        r'(?:Mun\.?|Municipio|Del\.?|Delegación|Alcaldía)\s+([^,\d]+)',
        addr, re_mod.IGNORECASE
    )
    if mun_match:
        result["address_municipio"] = mun_match.group(1).strip().rstrip(',')

    if "address_colonia" not in result or "address_municipio" not in result:
        parts = [p.strip() for p in addr.split(',') if p.strip()]
        if len(parts) >= 3:
            if "address_colonia" not in result:
                result["address_colonia"] = parts[-3] if len(parts) >= 4 else parts[-2]
            if "address_municipio" not in result and len(parts) >= 3:
                result["address_municipio"] = parts[-2]

    return result

def _validate_upload_file(file):
    """Validate uploaded file type, extension, and size."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no permitido. Solo CSV y XLSX.")
    ct = (file.content_type or "").lower()
    if ct and ct not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail=f"Tipo de archivo no permitido: {ct}")
