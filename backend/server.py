from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import pandas as pd
import io
import shutil

from middleware import AuditMiddleware, log_audit_event, log_system_error
from system_routes import create_system_router, SERVER_START_TIME
from kosmo_sync import create_kosmo_router, start_periodic_sync, stop_periodic_sync
from evidence_scoring import (
    evaluate_packages_for_journey,
    calculate_evidence_score,
    evaluate_single_package_for_journey,
    evaluate_single_package_ai,
)

import re as re_mod

def _next_day(date_str: str) -> str:
    """Given a date string 'YYYY-MM-DD', return the next day string."""
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return (dt + timedelta(days=1)).strftime("%Y-%m-%d")


def _normalize_address(address: str) -> dict:
    """
    Parse a Mexican address string to extract structured components.
    Returns dict with address_cp, address_colonia, address_municipio, address_estado.
    """
    if not address:
        return {}

    result = {}
    addr = address.strip()

    # Extract CP (5-digit postal code)
    cp_match = re_mod.search(r'\b(\d{5})\b', addr)
    if cp_match:
        result["address_cp"] = cp_match.group(1)

    # Common Mexican state abbreviations and names
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

    # Try to extract colonia (usually after "Col." or "Col " or "Colonia")
    col_match = re_mod.search(r'(?:Col\.?|Colonia)\s+([^,\d]+)', addr, re_mod.IGNORECASE)
    if col_match:
        result["address_colonia"] = col_match.group(1).strip().rstrip(',')

    # Try to extract municipio/delegación/alcaldía
    mun_match = re_mod.search(
        r'(?:Mun\.?|Municipio|Del\.?|Delegación|Alcaldía)\s+([^,\d]+)',
        addr, re_mod.IGNORECASE
    )
    if mun_match:
        result["address_municipio"] = mun_match.group(1).strip().rstrip(',')

    # If no colonia/municipio found, try splitting by commas
    if "address_colonia" not in result or "address_municipio" not in result:
        parts = [p.strip() for p in addr.split(',') if p.strip()]
        if len(parts) >= 3:
            if "address_colonia" not in result:
                result["address_colonia"] = parts[-3] if len(parts) >= 4 else parts[-2]
            if "address_municipio" not in result and len(parts) >= 3:
                result["address_municipio"] = parts[-2]

    return result


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'lastmile-os-secret-key-2026-production-v1')
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8

# File upload directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Create the main app
app = FastAPI(title="LastMile OS API")

# Store db on app state for middleware access
app.state.db = db

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str  # agent, coordinator, executive

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: str
    created_at: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class ClientBase(BaseModel):
    name: str

class ClientResponse(ClientBase):
    id: str

class ProviderBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None

class ProviderResponse(ProviderBase):
    id: str

class PackageBase(BaseModel):
    tracking_number: str
    recipient_name: str
    address: str
    zone: str
    delivery_window: str
    status: str = "pending"  # pending, delivered, failed, retry
    failure_reason: Optional[str] = None

class PackageResponse(PackageBase):
    id: str
    journey_id: str

class JourneyStartData(BaseModel):
    departure_time: str
    odometer_start: int = 0
    fuel_level: str = ""
    vehicle_condition: str = ""
    vehicle_notes: Optional[str] = None
    packages_loaded: int = 0
    notes: Optional[str] = None
    checklist_completed: bool = True
    arrival_time_cedis: Optional[str] = None
    backup_driver_name: Optional[str] = None
    backup_request_time: Optional[str] = None
    backup_arrival_time: Optional[str] = None
    route_type: Optional[str] = None
    city: Optional[str] = None
    max_packages: Optional[int] = None

class JourneyCloseData(BaseModel):
    closed_at: str
    odometer_end: int
    packages_delivered: int
    packages_failed: int
    notes: Optional[str] = None
    failed_packages: List[dict] = []
    checklist_completed: bool

class JourneyCreate(BaseModel):
    date: str
    client_id: str
    provider_id: str
    packages: List[dict]
    retry_packages: List[str] = []
    route_type: Optional[str] = "CDMX / Zona Metro"
    city: Optional[str] = None
    max_packages: Optional[int] = None

class JourneyResponse(BaseModel):
    id: str
    date: str
    client_id: str
    client_name: Optional[str] = None
    provider_id: str
    provider_name: Optional[str] = None
    status: str
    packages_total: int
    packages_delivered: int
    packages_failed: int
    packages_retry: int
    incidents_count: int
    start_data: Optional[dict] = None
    close_data: Optional[dict] = None
    created_at: str

class IncidentBase(BaseModel):
    journey_id: str
    occurred_at: str
    incident_type: str
    description: str
    severity: str  # Alto, Medio, Bajo
    tracking_number: Optional[str] = None
    action_taken: Optional[str] = None
    imputability: Optional[str] = "Por definir"  # "ME / Mensajero", "Cliente (destinatario)", "Por definir"

class IncidentCreate(IncidentBase):
    pass

class IncidentResponse(IncidentBase):
    id: str
    status: str  # open, resolved
    created_at: str
    resolved_at: Optional[str] = None

class PasswordResetRequest(BaseModel):
    user_id: str
    requested_at: str
    status: str  # pending, completed
    notes: Optional[str] = None

class PasswordResetRequestCreate(BaseModel):
    email: EmailStr

class PasswordChangeByAdmin(BaseModel):
    user_id: str
    new_password: str

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
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
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
            # Intersect with existing filter
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

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not verify_password(data.password, user["password"]):
        await log_audit_event(db, data.email, "", "login_failed", "user", "", details=f"Failed login for {data.email}", status="error")
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    token = create_token(user["id"], user["email"], user["role"])
    user_response = {k: v for k, v in user.items() if k != "password"}
    await log_audit_event(db, user["id"], user["role"], "login_success", "user", user["id"])
    return TokenResponse(access_token=token, user=user_response)

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

@api_router.post("/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    return {"message": "Sesión cerrada exitosamente"}

# ==================== USER MANAGEMENT (COORDINATOR ONLY) ====================

@api_router.get("/users")
async def get_users(user: dict = Depends(require_role(["coordinator", "developer"]))):
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(100)
    
    # Enrich with client and provider names
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    for u in users:
        assigned_clients = u.get("assigned_clients", [])
        assigned_providers = u.get("assigned_providers", [])
        u["assigned_client_names"] = [clients.get(cid, "") for cid in assigned_clients if cid in clients]
        u["assigned_provider_names"] = [providers.get(pid, "") for pid in assigned_providers if pid in providers]
    
    return users

@api_router.post("/users")
async def create_user(data: UserCreate, user: dict = Depends(require_role(["coordinator", "developer"]))):
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    new_user = {
        "id": str(uuid.uuid4()),
        "email": data.email,
        "name": data.name,
        "role": data.role,
        "password": hash_password(data.password),
        "assigned_clients": [],
        "assigned_providers": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(new_user)
    return {k: v for k, v in new_user.items() if k not in ["_id", "password"]}

@api_router.put("/users/{user_id}")
async def update_user(user_id: str, data: dict, admin: dict = Depends(require_role(["coordinator", "developer"]))):
    update_data = {k: v for k, v in data.items() if k not in ["id", "password", "_id"]}
    result = await db.users.update_one({"id": user_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Usuario actualizado"}

@api_router.put("/users/{user_id}/assignments")
async def update_user_assignments(
    user_id: str, 
    data: dict,
    admin: dict = Depends(require_role(["coordinator", "developer"]))
):
    """Update client and provider assignments for a user"""
    update_data = {}
    if "assigned_clients" in data:
        update_data["assigned_clients"] = data["assigned_clients"]
    if "assigned_providers" in data:
        update_data["assigned_providers"] = data["assigned_providers"]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")
    
    result = await db.users.update_one({"id": user_id}, {"$set": update_data})
    if result.modified_count == 0:
        # Check if user exists
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return {"message": "Asignaciones actualizadas"}

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Usuario eliminado"}

@api_router.post("/users/change-password")
async def change_password_by_admin(data: PasswordChangeByAdmin, admin: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.users.update_one(
        {"id": data.user_id},
        {"$set": {"password": hash_password(data.new_password)}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Mark any pending reset request as completed
    await db.password_reset_requests.update_many(
        {"user_id": data.user_id, "status": "pending"},
        {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Contraseña actualizada exitosamente"}

# ==================== PASSWORD RESET REQUESTS ====================

@api_router.post("/auth/request-password-reset")
async def request_password_reset(data: PasswordResetRequestCreate):
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user:
        # Don't reveal if email exists
        return {"message": "Si el email existe, se notificará al administrador"}
    
    request = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_email": user["email"],
        "user_name": user["name"],
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending"
    }
    await db.password_reset_requests.insert_one(request)
    return {"message": "Solicitud enviada. El administrador procesará tu solicitud."}

@api_router.get("/password-reset-requests")
async def get_password_reset_requests(admin: dict = Depends(require_role(["coordinator", "developer"]))):
    requests = await db.password_reset_requests.find({}, {"_id": 0}).sort("requested_at", -1).to_list(100)
    return requests

@api_router.delete("/password-reset-requests/{request_id}")
async def dismiss_password_reset_request(request_id: str, admin: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.password_reset_requests.delete_one({"id": request_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return {"message": "Solicitud eliminada"}

# ==================== CLIENTS ====================

@api_router.get("/clients", response_model=List[ClientResponse])
async def get_clients(user: dict = Depends(get_current_user)):
    clients = await db.clients.find({}, {"_id": 0}).to_list(100)
    return clients

@api_router.post("/clients", response_model=ClientResponse)
async def create_client(data: ClientBase, user: dict = Depends(require_role(["coordinator", "agent"]))):
    new_client = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.clients.insert_one(new_client)
    return {"id": new_client["id"], "name": new_client["name"]}

# ==================== PROVIDERS ====================

@api_router.get("/providers", response_model=List[ProviderResponse])
async def get_providers(user: dict = Depends(get_current_user)):
    providers = await db.providers.find({}, {"_id": 0}).to_list(100)
    return providers

@api_router.post("/providers", response_model=ProviderResponse)
async def create_provider(data: ProviderBase, user: dict = Depends(require_role(["coordinator", "agent"]))):
    new_provider = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "contact_name": data.contact_name,
        "contact_phone": data.contact_phone,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.providers.insert_one(new_provider)
    return {k: v for k, v in new_provider.items() if k != "_id"}

@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, data: dict, user: dict = Depends(require_role(["coordinator", "developer"]))):
    update_fields = {}
    if "name" in data:
        update_fields["name"] = data["name"]
    if not update_fields:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")
    result = await db.clients.update_one({"id": client_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"message": "Cliente actualizado"}

@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.clients.delete_one({"id": client_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"message": "Cliente eliminado"}

@api_router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, data: dict, user: dict = Depends(require_role(["coordinator", "developer"]))):
    update_fields = {}
    for field in ["name", "contact_name", "contact_phone"]:
        if field in data:
            update_fields[field] = data[field]
    if not update_fields:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")
    result = await db.providers.update_one({"id": provider_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return {"message": "Proveedor actualizado"}

@api_router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.providers.delete_one({"id": provider_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return {"message": "Proveedor eliminado"}

# ==================== DASHBOARD SEARCH ====================

@api_router.get("/packages/search")
async def search_packages(q: str, user: dict = Depends(get_current_user)):
    """Search packages by order_reference_id or tracking_number."""
    if not q or len(q) < 2:
        return []
    query = {
        "$or": [
            {"order_reference_id": {"$regex": q, "$options": "i"}},
            {"tracking_number": {"$regex": q, "$options": "i"}},
        ]
    }
    packages = await db.packages.find(query, {"_id": 0}).to_list(20)
    # Enrich with journey info
    journey_ids = list({p.get("journey_id") for p in packages if p.get("journey_id")})
    journeys = await db.journeys.find(
        {"id": {"$in": journey_ids}},
        {"_id": 0, "id": 1, "date": 1, "provider_name": 1, "client_name": 1}
    ).to_list(100)
    j_map = {j["id"]: j for j in journeys}
    for p in packages:
        j = j_map.get(p.get("journey_id"), {})
        p["journey_date"] = j.get("date")
        p["provider_name"] = j.get("provider_name")
        p["client_name"] = j.get("client_name")
    return packages

# ==================== JOURNEYS ====================

@api_router.get("/journeys")
async def get_journeys(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(get_current_user)
):
    query = {}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})["$lt"] = _next_day(date_to)
    if client_id:
        query["client_id"] = client_id
    if provider_id:
        query["provider_id"] = provider_id
    if status:
        query["status"] = status
    
    # Apply assignment-based filtering
    query = apply_assignment_filter(user, query)

    # Pagination
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    skip = (page - 1) * page_size

    total_count = await db.journeys.count_documents(query)
    total_pages = max(1, -(-total_count // page_size))  # ceil division

    journeys = await db.journeys.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(page_size).to_list(page_size)
    
    # Enrich with client and provider names
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    # Batch query incident counts to avoid N+1 problem
    journey_ids = [j["id"] for j in journeys]
    incident_counts = {}
    open_incident_counts = {}
    if journey_ids:
        pipeline_total = [
            {"$match": {"journey_id": {"$in": journey_ids}}},
            {"$group": {"_id": "$journey_id", "count": {"$sum": 1}}}
        ]
        pipeline_open = [
            {"$match": {"journey_id": {"$in": journey_ids}, "status": "open"}},
            {"$group": {"_id": "$journey_id", "count": {"$sum": 1}}}
        ]
        async for doc in db.incidents.aggregate(pipeline_total):
            incident_counts[doc["_id"]] = doc["count"]
        async for doc in db.incidents.aggregate(pipeline_open):
            open_incident_counts[doc["_id"]] = doc["count"]
    
    for j in journeys:
        j["client_name"] = clients.get(j.get("client_id"), "")
        j["provider_name"] = providers.get(j.get("provider_id"), "")
        j["incidents_count"] = incident_counts.get(j["id"], 0)
        j["open_incidents_count"] = open_incident_counts.get(j["id"], 0)
    
    return {
        "data": journeys,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        },
    }

@api_router.get("/journeys/{journey_id}")
async def get_journey(journey_id: str, user: dict = Depends(get_current_user)):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    
    # Get client and provider names
    client = await db.clients.find_one({"id": journey.get("client_id")}, {"_id": 0})
    provider = await db.providers.find_one({"id": journey.get("provider_id")}, {"_id": 0})
    journey["client_name"] = client["name"] if client else ""
    journey["provider_name"] = provider["name"] if provider else ""
    
    # Get packages
    packages = await db.packages.find({"journey_id": journey_id}, {"_id": 0}).to_list(1000)
    
    # Enrich with delivery_attempt count based on date ordering
    order_refs = [p.get("order_reference_id") for p in packages if p.get("order_reference_id")]
    if order_refs:
        # Get all packages with matching order_reference_ids and their journey dates
        sibling_pipeline = [
            {"$match": {"order_reference_id": {"$in": list(set(order_refs))}}},
            {"$lookup": {
                "from": "journeys",
                "localField": "journey_id",
                "foreignField": "id",
                "as": "journey_info"
            }},
            {"$unwind": {"path": "$journey_info", "preserveNullAndEmptyArrays": True}},
            {"$project": {
                "_id": 0,
                "order_reference_id": 1,
                "journey_id": 1,
                "journey_date": "$journey_info.date"
            }},
            {"$sort": {"journey_date": 1}}
        ]
        siblings = await db.packages.aggregate(sibling_pipeline).to_list(5000)
        
        # Group by order_reference_id, sorted by date ascending
        from collections import defaultdict
        ref_groups = defaultdict(list)
        for s in siblings:
            ref_groups[s["order_reference_id"]].append(s["journey_id"])
        
        # For each package, find its position (newest = 1, oldest = total)
        for p in packages:
            ref = p.get("order_reference_id", "")
            group = ref_groups.get(ref, [])
            total = len(set(group))
            if total <= 1:
                p["delivery_attempt"] = 1
            else:
                # Find position of this package's journey in the sorted list (oldest first)
                unique_journeys = list(dict.fromkeys(group))  # preserve order, dedup
                try:
                    pos = unique_journeys.index(p["journey_id"])
                    # Reverse: oldest journey gets highest number
                    p["delivery_attempt"] = total - pos
                except ValueError:
                    p["delivery_attempt"] = 1
    
    journey["packages"] = packages
    
    # Get incidents
    incidents = await db.incidents.find({"journey_id": journey_id}, {"_id": 0}).to_list(100)
    journey["incidents"] = incidents
    journey["incidents_count"] = len(incidents)
    journey["open_incidents_count"] = len([i for i in incidents if i["status"] == "open"])
    
    return journey

@api_router.post("/journeys")
async def create_journey(data: JourneyCreate, user: dict = Depends(require_role(["coordinator", "agent"]))):
    journey_id = str(uuid.uuid4())
    
    journey = {
        "id": journey_id,
        "date": data.date,
        "client_id": data.client_id,
        "provider_id": data.provider_id,
        "status": "scheduled",
        "route_type": data.route_type or "CDMX / Zona Metro",
        "city": data.city,
        "max_packages": data.max_packages,
        "packages_total": len(data.packages) + len(data.retry_packages),
        "packages_delivered": 0,
        "packages_failed": 0,
        "packages_retry": len(data.retry_packages),
        "start_data": None,
        "close_data": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"]
    }
    await db.journeys.insert_one(journey)
    
    # Create packages
    for pkg in data.packages:
        package = {
            "id": str(uuid.uuid4()),
            "journey_id": journey_id,
            "tracking_number": pkg.get("tracking_number", ""),
            "recipient_name": pkg.get("recipient_name", ""),
            "address": pkg.get("address", ""),
            "zone": pkg.get("zone", ""),
            "delivery_window": pkg.get("delivery_window", ""),
            "status": "pending",
            "is_retry": False
        }
        await db.packages.insert_one(package)
    
    # Link retry packages
    for pkg_id in data.retry_packages:
        await db.packages.update_one(
            {"id": pkg_id},
            {"$set": {"journey_id": journey_id, "status": "pending", "is_retry": True}}
        )
    
    return {"id": journey_id, "message": "Ruta creada exitosamente"}

@api_router.put("/journeys/{journey_id}/start")
async def start_journey(journey_id: str, data: JourneyStartData, user: dict = Depends(require_role(["coordinator", "agent"]))):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    
    if journey["status"] != "scheduled":
        raise HTTPException(status_code=400, detail="La ruta ya fue iniciada o cerrada")
    
    if not data.checklist_completed:
        raise HTTPException(status_code=400, detail="Debe completar el checklist antes de iniciar")
    
    start_data = {
        "departure_time": data.departure_time,
        "odometer_start": data.odometer_start,
        "fuel_level": data.fuel_level,
        "vehicle_condition": data.vehicle_condition,
        "vehicle_notes": data.vehicle_notes,
        "packages_loaded": data.packages_loaded,
        "notes": data.notes,
        "arrival_time_cedis": data.arrival_time_cedis,
        "backup_driver_name": data.backup_driver_name,
        "backup_request_time": data.backup_request_time,
        "backup_arrival_time": data.backup_arrival_time,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "started_by": user["id"]
    }
    
    update_fields = {"status": "in_progress", "start_data": start_data}
    # Store route_type from start form if provided
    if hasattr(data, 'route_type') and data.route_type:
        update_fields["route_type"] = data.route_type
    if hasattr(data, 'city') and data.city:
        update_fields["city"] = data.city
    if hasattr(data, 'max_packages') and data.max_packages:
        update_fields["max_packages"] = data.max_packages
    
    await db.journeys.update_one(
        {"id": journey_id},
        {"$set": update_fields}
    )
    await log_audit_event(db, user["id"], user["role"], "route_started", "journey", journey_id)
    
    return {"message": "Ruta iniciada exitosamente"}

@api_router.put("/journeys/{journey_id}/close")
async def close_journey(journey_id: str, data: JourneyCloseData, user: dict = Depends(require_role(["coordinator", "agent"]))):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    
    if journey["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="La ruta debe estar en progreso para cerrarla")
    
    if not data.checklist_completed:
        raise HTTPException(status_code=400, detail="Debe completar el checklist antes de cerrar")
    
    # Calculate metrics
    start_data = journey.get("start_data", {})
    odometer_start = start_data.get("odometer_start", 0)
    km_traveled = data.odometer_end - odometer_start
    packages_loaded = start_data.get("packages_loaded", journey["packages_total"])
    delivery_rate = (data.packages_delivered / packages_loaded * 100) if packages_loaded > 0 else 0
    packages_to_retry = packages_loaded - data.packages_delivered - data.packages_failed
    
    close_data = {
        "closed_at": data.closed_at,
        "odometer_end": data.odometer_end,
        "packages_delivered": data.packages_delivered,
        "packages_failed": data.packages_failed,
        "packages_to_retry": packages_to_retry,
        "km_traveled": km_traveled,
        "delivery_rate": round(delivery_rate, 2),
        "notes": data.notes,
        "closed_by": user["id"]
    }
    
    await db.journeys.update_one(
        {"id": journey_id},
        {"$set": {
            "status": "closed",
            "close_data": close_data,
            "packages_delivered": data.packages_delivered,
            "packages_failed": data.packages_failed
        }}
    )
    
    # Update return packages with status "returned"
    for failed_pkg in data.failed_packages:
        await db.packages.update_one(
            {"id": failed_pkg["id"]},
            {"$set": {"status": "returned", "failure_reason": failed_pkg.get("failure_reason", "")}}
        )
    
    await log_audit_event(db, user["id"], user["role"], "route_closed", "journey", journey_id)
    
    # Evaluate evidence quality for all packages in the closed route
    await evaluate_packages_for_journey(db, journey_id)
    
    return {"message": "Ruta cerrada exitosamente", "close_data": close_data}

# ==================== INCIDENTS ====================

@api_router.get("/incidents")
async def get_incidents(
    journey_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if journey_id:
        query["journey_id"] = journey_id
    if status:
        query["status"] = status
    
    incidents = await db.incidents.find(query, {"_id": 0}).sort("occurred_at", -1).to_list(500)
    return incidents

@api_router.post("/incidents", response_model=IncidentResponse)
async def create_incident(data: IncidentCreate, user: dict = Depends(require_role(["coordinator", "agent"]))):
    incident = {
        "id": str(uuid.uuid4()),
        "journey_id": data.journey_id,
        "occurred_at": data.occurred_at,
        "incident_type": data.incident_type,
        "description": data.description,
        "severity": data.severity,
        "tracking_number": data.tracking_number,
        "action_taken": data.action_taken,
        "imputability": data.imputability or "Por definir",
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"]
    }
    await db.incidents.insert_one(incident)
    await log_audit_event(db, user["id"], user["role"], "incident_created", "incident", incident["id"])
    return {k: v for k, v in incident.items() if k != "_id"}

@api_router.put("/incidents/{incident_id}")
async def update_incident(incident_id: str, data: dict, user: dict = Depends(require_role(["coordinator", "agent"]))):
    update_data = {k: v for k, v in data.items() if k not in ["id", "_id"]}
    
    if data.get("status") == "resolved":
        update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
        update_data["resolved_by"] = user["id"]
    
    result = await db.incidents.update_one({"id": incident_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    return {"message": "Incidencia actualizada"}

@api_router.delete("/incidents/{incident_id}")
async def delete_incident(incident_id: str, user: dict = Depends(require_role(["coordinator", "agent"]))):
    result = await db.incidents.delete_one({"id": incident_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    return {"message": "Incidencia eliminada"}

@api_router.put("/incidents/journey/{journey_id}/resolve-all")
async def resolve_all_incidents(journey_id: str, user: dict = Depends(require_role(["coordinator", "agent"]))):
    """Resolve all open incidents for a journey in a single operation."""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.incidents.update_many(
        {"journey_id": journey_id, "status": "open"},
        {"$set": {
            "status": "resolved",
            "resolved_at": now,
            "resolved_by": user["id"],
            "action_taken": "Resuelta en lote por el coordinador"
        }}
    )
    return {"message": f"{result.modified_count} incidencias resueltas", "resolved_count": result.modified_count}

@api_router.put("/packages/{package_id}/review")
async def review_package(package_id: str, user: dict = Depends(get_current_user)):
    """Mark a package as reviewed by the current user."""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.packages.update_one(
        {"id": package_id},
        {"$set": {
            "reviewed_by": user.get("name", user["email"]),
            "reviewed_at": now
        }}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return {"message": "Paquete marcado como revisado", "reviewed_by": user.get("name", user["email"]), "reviewed_at": now}

# ==================== FILE UPLOAD ====================

# Upload history-orders CSV file (Step 1)
@api_router.post("/upload/history-orders")
async def upload_history_orders(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    if not file.filename.endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos CSV o XLSX")
    
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede 10MB")
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Required columns from history-orders
        required_columns = ["order_id", "order_reference_id", "tracking_url"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(status_code=400, detail=f"Columnas faltantes: {', '.join(missing_columns)}")
        
        # Convert to list of dicts
        orders = df.to_dict('records')
        
        # Clean data and extract key fields
        cleaned_orders = []
        for order in orders:
            cleaned_order = {}
            for key in order:
                if pd.isna(order[key]):
                    cleaned_order[key] = ""
                else:
                    cleaned_order[key] = str(order[key])
            cleaned_orders.append(cleaned_order)
        
        # Auto-filter: discard invalid rows (P0)
        ignored_count = 0
        valid_orders = []
        for order in cleaned_orders:
            tracking = order.get("order_reference_id", "").strip()
            # Skip empty/null/whitespace tracking numbers
            if not tracking:
                ignored_count += 1
                continue
            # Skip OWN_FLEET with empty tracking
            provider_val = order.get("provider", "").strip()
            if provider_val.upper() == "OWN_FLEET" and not tracking:
                ignored_count += 1
                continue
            # Skip repeated header rows (first column value == column name)
            first_key = list(order.keys())[0] if order else ""
            first_val = order.get(first_key, "").strip().lower()
            if first_val == first_key.lower():
                ignored_count += 1
                continue
            valid_orders.append(order)
        cleaned_orders = valid_orders
        
        # Group orders by order_id (route)
        routes = {}
        for order in cleaned_orders:
            route_id = order.get("order_id", "")
            if route_id:
                if route_id not in routes:
                    routes[route_id] = {
                        "route_id": route_id,
                        "driver_name": order.get("driver_name", ""),
                        "orders": []
                    }
                routes[route_id]["orders"].append({
                    "order_reference_id": order.get("order_reference_id", ""),
                    "tracking_url": order.get("tracking_url", ""),
                    "recipient_name": order.get("recipient_name", ""),
                    "recipient_address": order.get("recipient_address", ""),
                    "recipient_phone": order.get("recipient_phone", ""),
                    "zone": order.get("zone", ""),
                    "order_status": order.get("order_status", ""),
                    "failure_reason": order.get("failure_reason", ""),
                    "failure_reason_note": order.get("failure_reason_note", ""),
                    "created_date": order.get("created_date", ""),
                    "created_at": order.get("created_at", "")
                })
        
        return {
            "filename": file.filename,
            "total_orders": len(cleaned_orders),
            "total_routes": len(routes),
            "ignored_rows": ignored_count,
            "routes": list(routes.values()),
            "preview": cleaned_orders[:10]
        }
    except Exception as e:
        logger.error(f"Error parsing history-orders file: {e}")
        raise HTTPException(status_code=400, detail=f"Error al procesar archivo: {str(e)}")

# Upload route-summary XLSX file (Step 2)
@api_router.post("/upload/route-summary")
async def upload_route_summary(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    if not file.filename.endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos CSV o XLSX")
    
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede 10MB")
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Required columns from route-summary
        required_columns = ["Order ID", "Driver"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(status_code=400, detail=f"Columnas faltantes: {', '.join(missing_columns)}")
        
        # Convert to list of dicts
        routes = df.to_dict('records')
        
        # Clean data
        cleaned_routes = []
        for route in routes:
            cleaned_route = {}
            for key in route:
                if pd.isna(route[key]):
                    cleaned_route[key] = ""
                else:
                    cleaned_route[key] = str(route[key])
            
            # Only include rows with valid Order ID
            if cleaned_route.get("Order ID"):
                cleaned_routes.append({
                    "route_id": cleaned_route.get("Order ID", ""),
                    "driver_name": cleaned_route.get("Driver", ""),
                    "team": cleaned_route.get("Team", ""),
                    "status": cleaned_route.get("Status", ""),
                    "zones": cleaned_route.get("Zones", ""),
                    "creation_date": cleaned_route.get("Creation Date", ""),
                    "planned_distance": cleaned_route.get("Planned Distance", ""),
                    "actual_distance": cleaned_route.get("Actual Distance", ""),
                    "total_stops": cleaned_route.get("Total Stops", "0"),
                    "completed_stops": cleaned_route.get("Completed Stops", "0"),
                    "cancelled_stops": cleaned_route.get("Cancelled Stops", "0"),
                    "pending_stops": cleaned_route.get("Pending Stops", "0")
                })
        
        # Get unique drivers for provider assignment
        drivers = list(set(r["driver_name"] for r in cleaned_routes if r["driver_name"]))
        
        return {
            "filename": file.filename,
            "total_routes": len(cleaned_routes),
            "routes": cleaned_routes,
            "drivers": sorted(drivers),
            "preview": cleaned_routes[:10]
        }
    except Exception as e:
        logger.error(f"Error parsing route-summary file: {e}")
        raise HTTPException(status_code=400, detail=f"Error al procesar archivo: {str(e)}")

# ==================== MESSENGER-PROVIDER MAPPING ====================

class MessengerProviderMapping(BaseModel):
    messenger_name: str
    provider_id: str

@api_router.get("/messenger-mappings")
async def get_messenger_mappings(user: dict = Depends(get_current_user)):
    mappings = await db.messenger_mappings.find({}, {"_id": 0}).to_list(500)
    # Enrich with provider names
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    for m in mappings:
        m["provider_name"] = providers.get(m.get("provider_id"), "Sin asignar")
    return mappings

@api_router.post("/messenger-mappings")
async def save_messenger_mappings(
    mappings: List[MessengerProviderMapping],
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    for mapping in mappings:
        await db.messenger_mappings.update_one(
            {"messenger_name": mapping.messenger_name},
            {"$set": {
                "messenger_name": mapping.messenger_name,
                "provider_id": mapping.provider_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": user["id"]
            }},
            upsert=True
        )
    return {"message": f"{len(mappings)} asignaciones guardadas"}

@api_router.delete("/messenger-mappings/{messenger_name}")
async def delete_messenger_mapping(
    messenger_name: str,
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    result = await db.messenger_mappings.delete_one({"messenger_name": messenger_name})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Mapping no encontrado")
    return {"message": "Asignación eliminada"}

# ==================== COMBINED JOURNEY CREATION (Two-step upload) ====================

class CosmoJourneyCreate(BaseModel):
    date: str
    client_id: str
    history_orders: List[dict]  # Orders from history-orders file
    route_summary: List[dict]   # Routes from route-summary file
    messenger_provider_mappings: List[dict]  # {messenger_name, provider_id}
    route_type: Optional[str] = "CDMX / Zona Metro"
    city: Optional[str] = None
    max_packages: Optional[int] = None

@api_router.post("/journeys/from-cosmo")
async def create_journeys_from_cosmo(
    data: CosmoJourneyCreate,
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    created_journeys = []
    updated_journeys = []
    skipped_duplicates = []
    errors = []
    total_new_packages = 0
    total_updated_packages = 0
    
    # Save messenger-provider mappings
    for mapping in data.messenger_provider_mappings:
        if mapping.get("messenger_name") and mapping.get("provider_id"):
            await db.messenger_mappings.update_one(
                {"messenger_name": mapping["messenger_name"]},
                {"$set": {
                    "messenger_name": mapping["messenger_name"],
                    "provider_id": mapping["provider_id"],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
    
    # Get all existing orders to check for duplicates using composite key (cosmo_route_id + order_reference_id)
    existing_orders = await db.packages.find({}, {"order_reference_id": 1, "cosmo_route_id": 1, "id": 1, "journey_id": 1, "_id": 0}).to_list(10000)
    existing_order_map = {}
    # Count previous attempts per order_reference_id
    attempt_counts = {}
    for o in existing_orders:
        ref = o.get("order_reference_id", "")
        route = o.get("cosmo_route_id", "")
        if ref:
            composite_key = f"{route}|{ref}"
            existing_order_map[composite_key] = o
            attempt_counts[ref] = attempt_counts.get(ref, 0) + 1
    
    # Build order lookup from history-orders
    orders_by_route = {}
    for order in data.history_orders:
        route_id = order.get("order_id") or order.get("route_id", "")
        if route_id:
            if route_id not in orders_by_route:
                orders_by_route[route_id] = []
            orders_by_route[route_id].append(order)
    
    # Get messenger-provider mappings
    mappings = {m["messenger_name"]: m["provider_id"] for m in data.messenger_provider_mappings if m.get("provider_id")}
    
    # Process each route from route-summary
    for route in data.route_summary:
        route_id = route.get("route_id", "")
        driver_name = route.get("driver_name", "")
        
        if not route_id:
            continue
        
        # Get provider from mapping
        provider_id = mappings.get(driver_name)
        if not provider_id:
            existing_mapping = await db.messenger_mappings.find_one({"messenger_name": driver_name}, {"_id": 0})
            if existing_mapping:
                provider_id = existing_mapping.get("provider_id")
        
        if not provider_id:
            errors.append(f"Sin proveedor asignado para mensajero: {driver_name}")
            continue
        
        # Check if journey with this route_id already exists
        existing_journey = await db.journeys.find_one({"cosmo_route_id": route_id}, {"_id": 0})
        
        # Get orders for this route
        route_orders = orders_by_route.get(route_id, [])
        
        if existing_journey:
            # UPDATE MODE: Update existing packages' status
            route_updated = 0
            for order in route_orders:
                order_ref = order.get("order_reference_id", "")
                composite_key = f"{route_id}|{order_ref}"
                if order_ref and composite_key in existing_order_map:
                    # Update existing package in this route
                    update_fields = {}
                    new_cosmo_status = order.get("order_status", "")
                    if new_cosmo_status:
                        update_fields["cosmo_status"] = new_cosmo_status
                        if new_cosmo_status == "delivered":
                            update_fields["status"] = "delivered"
                        elif new_cosmo_status == "cancelled":
                            update_fields["status"] = "failed"
                    
                    tracking_url = order.get("tracking_url", "")
                    if tracking_url:
                        update_fields["tracking_url"] = tracking_url
                    
                    if update_fields:
                        pkg_data = existing_order_map[composite_key]
                        if isinstance(pkg_data, dict) and "id" in pkg_data:
                            await db.packages.update_one(
                                {"id": pkg_data["id"]},
                                {"$set": update_fields}
                            )
                            route_updated += 1
            
            # Recalculate journey counts
            if route_updated > 0:
                j_id = existing_journey["id"]
                delivered = await db.packages.count_documents({"journey_id": j_id, "status": "delivered"})
                failed = await db.packages.count_documents({"journey_id": j_id, "status": "failed"})
                await db.journeys.update_one(
                    {"id": j_id},
                    {"$set": {"packages_delivered": delivered, "packages_failed": failed}}
                )
                total_updated_packages += route_updated
                updated_journeys.append({
                    "journey_id": j_id,
                    "route_id": route_id,
                    "driver": driver_name,
                    "packages_updated": route_updated
                })
            continue
        
        # CREATE MODE: New journey
        new_orders = []
        updated_in_other = 0
        for order in route_orders:
            order_ref = order.get("order_reference_id", "")
            composite_key = f"{route_id}|{order_ref}"
            if composite_key in existing_order_map:
                pkg_data = existing_order_map[composite_key]
                # Only update if pkg_data is a real document (not a placeholder)
                if isinstance(pkg_data, dict) and "id" in pkg_data:
                    update_fields = {}
                    new_cosmo_status = order.get("order_status", "")
                    if new_cosmo_status:
                        update_fields["cosmo_status"] = new_cosmo_status
                        if new_cosmo_status == "delivered":
                            update_fields["status"] = "delivered"
                        elif new_cosmo_status == "cancelled":
                            update_fields["status"] = "failed"
                    tracking_url = order.get("tracking_url", "")
                    if tracking_url:
                        update_fields["tracking_url"] = tracking_url
                    if update_fields:
                        await db.packages.update_one({"id": pkg_data["id"]}, {"$set": update_fields})
                        updated_in_other += 1
                        total_updated_packages += 1
                else:
                    # Placeholder from this same batch — skip (already queued as new_order)
                    pass
            else:
                # New order in this route (could be a re-attempt of an existing order_ref in another route)
                new_orders.append(order)
                existing_order_map[composite_key] = True
                attempt_counts[order_ref] = attempt_counts.get(order_ref, 0) + 1
        
        if not new_orders and route_orders:
            if updated_in_other > 0:
                updated_journeys.append({
                    "route_id": route_id,
                    "driver": driver_name,
                    "packages_updated": updated_in_other
                })
            else:
                skipped_duplicates.append(f"{route_id} (todas las órdenes duplicadas)")
            continue
        
        # Create journey - use creation_date from route-summary if available, else fallback to payload date
        route_creation_date = route.get("creation_date", "")
        journey_date = route_creation_date if route_creation_date else data.date
        # Normalize date format (e.g., "2026-03-21T00:00:00" → "2026-03-21")
        if journey_date and "T" in journey_date:
            journey_date = journey_date.split("T")[0]
        
        journey_id = str(uuid.uuid4())
        journey = {
            "id": journey_id,
            "cosmo_route_id": route_id,
            "date": journey_date,
            "client_id": data.client_id,
            "provider_id": provider_id,
            "driver_name": driver_name,
            "team": route.get("team", ""),
            "status": "scheduled",
            "route_type": data.route_type or "CDMX / Zona Metro",
            "city": data.city if data.route_type == "Foránea" else None,
            "max_packages": data.max_packages if data.route_type == "Foránea" else None,
            "packages_total": len(new_orders),
            "packages_delivered": 0,
            "packages_failed": 0,
            "packages_retry": 0,
            "planned_distance": route.get("planned_distance", ""),
            "actual_distance": route.get("actual_distance", ""),
            "total_stops": route.get("total_stops", "0"),
            "completed_stops": route.get("completed_stops", "0"),
            "cancelled_stops": route.get("cancelled_stops", "0"),
            "start_data": None,
            "close_data": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user["id"]
        }
        await db.journeys.insert_one(journey)
        
        # Create packages from orders
        for order in new_orders:
            order_ref = order.get("order_reference_id", "")
            package = {
                "id": str(uuid.uuid4()),
                "journey_id": journey_id,
                "cosmo_route_id": route_id,
                "order_reference_id": order_ref,
                "tracking_number": order_ref,
                "tracking_url": order.get("tracking_url", ""),
                "recipient_name": order.get("recipient_name", ""),
                "address": order.get("recipient_address", ""),
                "recipient_phone": order.get("recipient_phone", ""),
                "zone": order.get("zone", ""),
                "delivery_window": "",
                "cosmo_status": order.get("order_status", ""),
                "status": "delivered" if order.get("order_status") == "delivered" else ("failed" if order.get("order_status") == "cancelled" else "pending"),
                "failure_reason": order.get("failure_reason", ""),
                "failure_reason_note": order.get("failure_reason_note", ""),
                "created_date": order.get("created_date", ""),
                "delivery_attempt": attempt_counts.get(order_ref, 1),
                "is_retry": attempt_counts.get(order_ref, 1) > 1,
                **_normalize_address(order.get("recipient_address", "")),
            }
            await db.packages.insert_one(package)
            total_new_packages += 1
            
            if package["status"] == "delivered":
                await db.journeys.update_one({"id": journey_id}, {"$inc": {"packages_delivered": 1}})
            elif package["status"] == "failed":
                await db.journeys.update_one({"id": journey_id}, {"$inc": {"packages_failed": 1}})
        
        created_journeys.append({
            "journey_id": journey_id,
            "route_id": route_id,
            "driver": driver_name,
            "packages": len(new_orders),
            "duplicates_updated": updated_in_other
        })
    
    await log_audit_event(db, user["id"], user["role"], "layout_uploaded", "layout", "", details=f"{len(created_journeys)} rutas, {total_new_packages} nuevos, {total_updated_packages} actualizados")

    return {
        "message": f"{len(created_journeys)} rutas creadas, {total_updated_packages} paquetes actualizados",
        "created_journeys": created_journeys,
        "updated_journeys": updated_journeys,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
        "total_new_packages": total_new_packages,
        "total_updated_packages": total_updated_packages
    }

# Keep original layout upload for backwards compatibility
@api_router.post("/upload/layout")
async def upload_layout(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    # Validate file type
    if not file.filename.endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos CSV o XLSX")
    
    # Check file size (5MB max)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede 5MB")
    
    try:
        # Parse file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Validate required columns
        required_columns = ["tracking_number", "recipient_name", "address", "zone", "delivery_window"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(
                status_code=400,
                detail=f"Columnas faltantes: {', '.join(missing_columns)}"
            )
        
        # Convert to list of dicts
        packages = df.to_dict('records')
        
        # Clean data
        for pkg in packages:
            for key in pkg:
                if pd.isna(pkg[key]):
                    pkg[key] = ""
                else:
                    pkg[key] = str(pkg[key])
        
        return {
            "filename": file.filename,
            "total_rows": len(packages),
            "preview": packages[:10],
            "packages": packages
        }
    except Exception as e:
        logger.error(f"Error parsing file: {e}")
        raise HTTPException(status_code=400, detail=f"Error al procesar archivo: {str(e)}")

@api_router.post("/upload/photo")
async def upload_photo(
    file: UploadFile = File(...),
    journey_id: str = Form(...),
    photo_type: str = Form(...),
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    # Validate file type
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos JPG o PNG")
    
    # Check file size (5MB max)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede 5MB")
    
    # Save file
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    filename = f"{journey_id}_{photo_type}_{file_id}{ext}"
    filepath = UPLOAD_DIR / filename
    
    with open(filepath, "wb") as f:
        f.write(contents)
    
    return {"filename": filename, "path": f"/api/uploads/{filename}"}

# Upload multiple images for journey sections
@api_router.post("/upload/journey-images")
async def upload_journey_images(
    files: List[UploadFile] = File(...),
    journey_id: str = Form(...),
    section: str = Form(...),  # start, incident, close
    incident_id: Optional[str] = Form(None),
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    uploaded_files = []
    
    for file in files:
        # Validate file type
        if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            continue
        
        # Save file
        file_id = str(uuid.uuid4())
        ext = Path(file.filename).suffix.lower()
        filename = f"{journey_id}_{section}_{file_id}{ext}"
        filepath = UPLOAD_DIR / filename
        
        with open(filepath, "wb") as f:
            f.write(contents)
        
        image_record = {
            "id": file_id,
            "journey_id": journey_id,
            "section": section,
            "incident_id": incident_id,
            "filename": filename,
            "original_name": file.filename,
            "path": f"/api/uploads/{filename}",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_by": user["id"]
        }
        await db.journey_images.insert_one(image_record)
        uploaded_files.append({k: v for k, v in image_record.items() if k != "_id"})
    
    return {"uploaded": len(uploaded_files), "files": uploaded_files}

# Get images for a journey section
@api_router.get("/journey-images/{journey_id}")
async def get_journey_images(
    journey_id: str,
    section: Optional[str] = None,
    incident_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {"journey_id": journey_id}
    if section:
        query["section"] = section
    if incident_id:
        query["incident_id"] = incident_id
    
    images = await db.journey_images.find(query, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
    return images

# Delete an image
@api_router.delete("/journey-images/{image_id}")
async def delete_journey_image(
    image_id: str,
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    image = await db.journey_images.find_one({"id": image_id}, {"_id": 0})
    if not image:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    
    # Delete file from filesystem
    filepath = UPLOAD_DIR / image["filename"]
    if filepath.exists():
        filepath.unlink()
    
    # Delete from database
    await db.journey_images.delete_one({"id": image_id})
    return {"message": "Imagen eliminada"}

@api_router.get("/uploads/{filename}")
async def get_upload(filename: str):
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    from fastapi.responses import FileResponse
    return FileResponse(filepath)

@api_router.get("/template/layout")
async def download_template():
    from fastapi.responses import Response
    
    template_data = "tracking_number,recipient_name,address,zone,delivery_window\nTRK001,Juan Pérez,Calle 123 Col Centro,Zona Norte,09:00-12:00\nTRK002,María García,Av Principal 456,Zona Sur,12:00-15:00"
    
    return Response(
        content=template_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantilla_layout.csv"}
    )

# ==================== RETRY PACKAGES ====================

@api_router.get("/retry-packages/{provider_id}")
async def get_retry_packages(provider_id: str, user: dict = Depends(get_current_user)):
    # Get packages from previous journeys that need retry
    packages = await db.packages.find(
        {"status": "retry"},
        {"_id": 0}
    ).to_list(500)
    
    # Filter by provider through journey
    retry_packages = []
    for pkg in packages:
        journey = await db.journeys.find_one({"id": pkg.get("journey_id")}, {"_id": 0})
        if journey and journey.get("provider_id") == provider_id:
            pkg["original_journey_date"] = journey.get("date", "")
            retry_packages.append(pkg)
    
    return retry_packages

# ==================== DASHBOARD / STATS ====================

@api_router.get("/dashboard/stats")
async def get_dashboard_stats(
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    # Support both single date and range
    if date_from and date_to:
        base_query = {"date": {"$gte": date_from, "$lt": _next_day(date_to)}}
    elif date:
        base_query = {"date": {"$gte": date, "$lt": _next_day(date)}}
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        base_query = {"date": {"$gte": today, "$lt": _next_day(today)}}
    
    base_query = apply_assignment_filter(user, base_query)
    
    # Active journeys today
    active_q = {**base_query, "status": "in_progress"}
    active_journeys = await db.journeys.count_documents(active_q)
    
    # Closed journeys today
    closed_q = {**base_query, "status": "closed"}
    closed_journeys = await db.journeys.count_documents(closed_q)
    
    # Total journeys today
    total_journeys = await db.journeys.count_documents(base_query)
    
    # Packages stats — count from actual package data
    journeys_today = await db.journeys.find(base_query, {"_id": 0}).to_list(500)
    journey_ids = [j["id"] for j in journeys_today]
    
    total_packages = await db.packages.count_documents({"journey_id": {"$in": journey_ids}})
    delivered_packages = await db.packages.count_documents({"journey_id": {"$in": journey_ids}, "status": "delivered"})
    
    # Open incidents
    open_incidents = await db.incidents.count_documents({
        "journey_id": {"$in": journey_ids},
        "status": "open"
    })
    
    # Delivery rate
    delivery_rate = (delivered_packages / total_packages * 100) if total_packages > 0 else 0
    
    # Total km traveled
    total_km = 0
    for j in journeys_today:
        close_data = j.get("close_data", {})
        if close_data:
            total_km += close_data.get("km_traveled", 0)
    
    # Evidence quality stats for today's closed routes
    closed_journey_ids = [j["id"] for j in journeys_today if j.get("status") == "closed"]
    avg_evidence_score = 0
    packages_incomplete = 0
    if closed_journey_ids:
        scored_pkgs = await db.packages.find(
            {"journey_id": {"$in": closed_journey_ids}, "evidence_score": {"$ne": None}},
            {"_id": 0, "evidence_score": 1}
        ).to_list(10000)
        if scored_pkgs:
            scores = [p["evidence_score"] for p in scored_pkgs]
            avg_evidence_score = round(sum(scores) / len(scores), 1)
            packages_incomplete = sum(1 for s in scores if s < 100)

    return {
        "date": date,
        "active_journeys": active_journeys,
        "closed_journeys": closed_journeys,
        "total_journeys": total_journeys,
        "total_packages": total_packages,
        "delivered_packages": delivered_packages,
        "delivery_rate": round(delivery_rate, 2),
        "open_incidents": open_incidents,
        "total_km": total_km,
        "avg_evidence_score": avg_evidence_score,
        "packages_incomplete_support": packages_incomplete,
    }

@api_router.get("/dashboard/incidents-breakdown")
async def get_incidents_breakdown(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    if not date_from:
        date_from = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not date_to:
        date_to = date_from
    
    # Get journeys in date range with assignment filtering
    j_query = {"date": {"$gte": date_from, "$lt": _next_day(date_to)}}
    j_query = apply_assignment_filter(user, j_query)
    
    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(500)
    journey_ids = [j["id"] for j in journeys]
    
    # Get incidents
    incidents = await db.incidents.find(
        {"journey_id": {"$in": journey_ids}},
        {"_id": 0}
    ).to_list(1000)
    
    # Group by type
    breakdown = {}
    for inc in incidents:
        inc_type = inc.get("incident_type", "Otro")
        breakdown[inc_type] = breakdown.get(inc_type, 0) + 1
    
    return breakdown

@api_router.get("/dashboard/provider-comparison")
async def get_provider_comparison(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    if not date_from:
        date_from = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not date_to:
        date_to = date_from
    
    # Get all providers (filtered by assignments if applicable)
    providers = await db.providers.find({}, {"_id": 0}).to_list(100)
    assigned_providers = user.get("assigned_providers", [])
    if assigned_providers:
        providers = [p for p in providers if p["id"] in assigned_providers]
    
    assigned_clients = user.get("assigned_clients", [])
    
    comparison = []
    for provider in providers:
        j_query = {
            "provider_id": provider["id"],
            "date": {"$gte": date_from, "$lt": _next_day(date_to)}
        }
        if assigned_clients:
            j_query["client_id"] = {"$in": assigned_clients}
        
        journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(500)
        
        if not journeys:
            continue
        
        total_journeys = len(journeys)
        total_delivered = sum(j.get("packages_delivered", 0) for j in journeys)
        total_packages = sum(j.get("packages_total", 0) for j in journeys)
        total_km = sum((j.get("close_data") or {}).get("km_traveled", 0) for j in journeys)
        
        # Get incidents count
        journey_ids = [j["id"] for j in journeys]
        incidents_count = await db.incidents.count_documents({"journey_id": {"$in": journey_ids}})
        
        avg_delivery_rate = (total_delivered / total_packages * 100) if total_packages > 0 else 0
        
        comparison.append({
            "provider_id": provider["id"],
            "provider_name": provider["name"],
            "journeys_count": total_journeys,
            "avg_delivery_rate": round(avg_delivery_rate, 2),
            "total_incidents": incidents_count,
            "total_km": total_km
        })
    
    return comparison

# ==================== UPLOAD HISTORY ====================

@api_router.get("/upload-history")
async def get_upload_history(user: dict = Depends(get_current_user)):
    history = await db.upload_history.find({}, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
    
    # Enrich with names
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    for h in history:
        h["client_name"] = clients.get(h.get("client_id"), "")
        h["provider_name"] = providers.get(h.get("provider_id"), "")
    
    return history

@api_router.post("/upload-history")
async def create_upload_history(data: dict, user: dict = Depends(require_role(["coordinator", "agent"]))):
    history_entry = {
        "id": str(uuid.uuid4()),
        "date": data.get("date"),
        "client_id": data.get("client_id"),
        "provider_id": data.get("provider_id"),
        "package_count": data.get("package_count", 0),
        "journey_id": data.get("journey_id"),
        "journey_status": data.get("journey_status", "scheduled"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": user["id"]
    }
    await db.upload_history.insert_one(history_entry)
    return history_entry

# ==================== EXPORT ====================

@api_router.get("/export/journeys")
async def export_journeys(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    from fastapi.responses import Response
    
    query = {}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})["$lte"] = date_to
    if client_id:
        query["client_id"] = client_id
    if provider_id:
        query["provider_id"] = provider_id
    
    journeys = await db.journeys.find(query, {"_id": 0}).to_list(1000)
    
    # Enrich with names
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    export_data = []
    for j in journeys:
        close_data = j.get("close_data") or {}
        start_data = j.get("start_data") or {}
        export_data.append({
            "Fecha": j.get("date", ""),
            "Cliente": clients.get(j.get("client_id"), ""),
            "Proveedor": providers.get(j.get("provider_id"), ""),
            "Estado": j.get("status", ""),
            "Paquetes Total": j.get("packages_total", 0),
            "Entregados": j.get("packages_delivered", 0),
            "Fallidos": j.get("packages_failed", 0),
            "Km Recorridos": close_data.get("km_traveled", 0),
            "Tasa Entrega (%)": close_data.get("delivery_rate", 0),
            "Hora Inicio": start_data.get("departure_time", ""),
            "Hora Cierre": close_data.get("closed_at", "")
        })
    
    df = pd.DataFrame(export_data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=rutas_export_{datetime.now().strftime('%Y%m%d')}.xlsx"}
    )

@api_router.get("/export/incidents")
async def export_incidents(
    journey_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    from fastapi.responses import Response
    
    query = {}
    if journey_id:
        query["journey_id"] = journey_id
    
    if date_from or date_to:
        # Get journeys in date range
        j_query = {}
        if date_from:
            j_query["date"] = {"$gte": date_from}
        if date_to:
            j_query.setdefault("date", {})["$lte"] = date_to
        journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(500)
        query["journey_id"] = {"$in": [j["id"] for j in journeys]}
    
    incidents = await db.incidents.find(query, {"_id": 0}).to_list(1000)
    
    export_data = []
    for inc in incidents:
        export_data.append({
            "Fecha/Hora": inc.get("occurred_at", ""),
            "Tipo": inc.get("incident_type", ""),
            "Descripción": inc.get("description", ""),
            "Severidad": inc.get("severity", ""),
            "Imputabilidad": inc.get("imputability", "Por definir"),
            "No. Guía": inc.get("tracking_number", ""),
            "Estado": inc.get("status", ""),
            "Acción Tomada": inc.get("action_taken", "")
        })
    
    df = pd.DataFrame(export_data)
    output = io.StringIO()
    df.to_csv(output, index=False)
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=incidencias_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

# ==================== SEED DATA ====================

@api_router.post("/seed")
async def seed_database():
    """Seed database with initial data"""
    
    # Check if already seeded
    existing_users = await db.users.count_documents({})
    if existing_users > 0:
        return {"message": "Base de datos ya tiene datos"}
    
    # Create clients
    clients = [
        {"id": str(uuid.uuid4()), "name": "Cubbo", "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Grupo Nadro", "created_at": datetime.now(timezone.utc).isoformat()}
    ]
    await db.clients.insert_many(clients)
    
    # Create providers
    providers = [
        {
            "id": str(uuid.uuid4()),
            "name": "Chamedé Logistics",
            "contact_name": "Chamedé",
            "contact_phone": "+52 55 0000 0001",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Octavio Transport",
            "contact_name": "Octavio",
            "contact_phone": "+52 55 0000 0002",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    await db.providers.insert_many(providers)
    
    # Create users
    password_hash = hash_password("LastMile2026")
    users = [
        {
            "id": str(uuid.uuid4()),
            "email": "agente@me.mx",
            "name": "Agente ME",
            "role": "agent",
            "password": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "yael@me.mx",
            "name": "Yael Coordinador",
            "role": "coordinator",
            "password": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "karina@me.mx",
            "name": "Karina Ejecutivo",
            "role": "executive",
            "password": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "email": "dev@me.mx",
            "name": "Dev Admin",
            "role": "developer",
            "password": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    await db.users.insert_many(users)
    
    # Create sample journeys
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Journey 1 - In progress
    journey1_id = str(uuid.uuid4())
    journey1 = {
        "id": journey1_id,
        "date": today,
        "client_id": clients[0]["id"],
        "provider_id": providers[0]["id"],
        "status": "in_progress",
        "packages_total": 25,
        "packages_delivered": 15,
        "packages_failed": 2,
        "packages_retry": 3,
        "start_data": {
            "departure_time": f"{today}T08:30:00",
            "odometer_start": 45230,
            "fuel_level": "Lleno",
            "vehicle_condition": "Bueno",
            "packages_loaded": 25,
            "started_at": datetime.now(timezone.utc).isoformat()
        },
        "close_data": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.journeys.insert_one(journey1)
    
    # Journey 2 - Closed
    journey2_id = str(uuid.uuid4())
    journey2 = {
        "id": journey2_id,
        "date": yesterday,
        "client_id": clients[1]["id"],
        "provider_id": providers[1]["id"],
        "status": "closed",
        "packages_total": 30,
        "packages_delivered": 27,
        "packages_failed": 2,
        "packages_retry": 1,
        "start_data": {
            "departure_time": f"{yesterday}T09:00:00",
            "odometer_start": 44800,
            "fuel_level": "3/4",
            "vehicle_condition": "Bueno",
            "packages_loaded": 30,
            "started_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        },
        "close_data": {
            "closed_at": f"{yesterday}T18:30:00",
            "odometer_end": 44950,
            "packages_delivered": 27,
            "packages_failed": 2,
            "packages_to_retry": 1,
            "km_traveled": 150,
            "delivery_rate": 90.0
        },
        "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    }
    await db.journeys.insert_one(journey2)
    
    # Create packages for journeys
    for i in range(25):
        pkg = {
            "id": str(uuid.uuid4()),
            "journey_id": journey1_id,
            "tracking_number": f"TRK{1000+i}",
            "recipient_name": f"Cliente {i+1}",
            "address": f"Calle {i+1} #100, Col. Centro",
            "zone": "Zona Norte" if i < 12 else "Zona Sur",
            "delivery_window": "09:00-12:00" if i < 12 else "12:00-15:00",
            "status": "delivered" if i < 15 else ("failed" if i < 17 else "pending"),
            "is_retry": i >= 22
        }
        await db.packages.insert_one(pkg)
    
    for i in range(30):
        pkg = {
            "id": str(uuid.uuid4()),
            "journey_id": journey2_id,
            "tracking_number": f"TRK{2000+i}",
            "recipient_name": f"Cliente {i+1}",
            "address": f"Av Principal {i*10}, Col. Industrial",
            "zone": "Zona Industrial",
            "delivery_window": "10:00-14:00",
            "status": "delivered" if i < 27 else ("failed" if i < 29 else "retry"),
            "is_retry": False
        }
        await db.packages.insert_one(pkg)
    
    # Create sample incidents
    incidents = [
        {
            "id": str(uuid.uuid4()),
            "journey_id": journey1_id,
            "occurred_at": f"{today}T10:30:00",
            "incident_type": "Destinatario ausente",
            "description": "Cliente no se encontraba en domicilio",
            "severity": "Bajo",
            "tracking_number": "TRK1015",
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "journey_id": journey1_id,
            "occurred_at": f"{today}T12:15:00",
            "incident_type": "Tiempo excesivo por entrega",
            "description": "Tráfico intenso en zona centro",
            "severity": "Medio",
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "journey_id": journey2_id,
            "occurred_at": f"{yesterday}T14:00:00",
            "incident_type": "Llanta ponchada",
            "description": "Se reventó llanta trasera derecha",
            "severity": "Alto",
            "action_taken": "Se cambió por llanta de refacción",
            "status": "resolved",
            "resolved_at": f"{yesterday}T15:30:00",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        }
    ]
    await db.incidents.insert_many(incidents)
    
    return {
        "message": "Base de datos inicializada exitosamente",
        "data": {
            "clients": len(clients),
            "providers": len(providers),
            "users": len(users),
            "journeys": 2,
            "packages": 55,
            "incidents": len(incidents)
        }
    }

@api_router.post("/cleanup/routes-packages")
async def cleanup_routes_packages(user: dict = Depends(require_role(["coordinator", "developer"]))):
    """Clear all journeys, packages, and incidents data for fresh testing."""
    j_del = await db.journeys.delete_many({})
    p_del = await db.packages.delete_many({})
    i_del = await db.incidents.delete_many({})
    return {
        "message": "Datos limpiados",
        "deleted": {
            "journeys": j_del.deleted_count,
            "packages": p_del.deleted_count,
            "incidents": i_del.deleted_count,
        }
    }

# ==================== CUSTOM REPORT GENERATION ====================

class ReportRequest(BaseModel):
    date_from: str
    date_to: str
    sections: List[str] = []  # provider_metrics, driver_metrics, incidents_breakdown, imputability
    group_by: Optional[str] = "provider"

@api_router.post("/reports/generate")
async def generate_report(
    data: ReportRequest,
    user: dict = Depends(get_current_user)
):
    """Generate custom report with AI insights"""
    from fpdf import FPDF
    from fastapi.responses import Response as FastResponse
    
    j_query = {"date": {"$gte": data.date_from, "$lte": data.date_to}}
    j_query = apply_assignment_filter(user, j_query)
    
    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    
    if not journeys:
        return {"error": "No hay datos para el período seleccionado"}
    
    journey_ids = [j["id"] for j in journeys]
    
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    incidents = await db.incidents.find({"journey_id": {"$in": journey_ids}}, {"_id": 0}).to_list(10000)
    
    # Build report data
    report_data = {
        "period": f"{data.date_from} - {data.date_to}",
        "total_journeys": len(journeys),
        "total_packages": sum(j.get("packages_total", 0) for j in journeys),
        "total_delivered": sum(j.get("packages_delivered", 0) for j in journeys),
        "total_failed": sum(j.get("packages_failed", 0) for j in journeys),
        "total_km": sum((j.get("close_data") or {}).get("km_traveled", 0) for j in journeys),
        "total_incidents": len(incidents),
    }
    
    total_pkg = report_data["total_packages"]
    report_data["delivery_rate"] = round((report_data["total_delivered"] / total_pkg * 100) if total_pkg > 0 else 0, 2)
    report_data["total_retry"] = total_pkg - report_data["total_delivered"] - report_data["total_failed"]
    
    # Provider metrics
    provider_metrics = {}
    for j in journeys:
        pid = j.get("provider_id", "")
        pname = providers.get(pid, "Sin proveedor")
        if pname not in provider_metrics:
            provider_metrics[pname] = {
                "days_operated": set(), "routes": 0, "packages_loaded": 0,
                "delivered": 0, "failed": 0, "km_total": 0
            }
        pm = provider_metrics[pname]
        pm["days_operated"].add(j.get("date", ""))
        pm["routes"] += 1
        pm["packages_loaded"] += j.get("packages_total", 0)
        pm["delivered"] += j.get("packages_delivered", 0)
        pm["failed"] += j.get("packages_failed", 0)
        pm["km_total"] += (j.get("close_data") or {}).get("km_traveled", 0)
    
    for pname in provider_metrics:
        pm = provider_metrics[pname]
        pm["days_operated"] = len(pm["days_operated"])
        pm["retry"] = pm["packages_loaded"] - pm["delivered"] - pm["failed"]
        pm["delivery_rate"] = round((pm["delivered"] / pm["packages_loaded"] * 100) if pm["packages_loaded"] > 0 else 0, 2)
    
    # Driver metrics
    driver_metrics = {}
    for j in journeys:
        dname = j.get("driver_name", "Sin driver")
        if not dname:
            dname = "Sin driver"
        if dname not in driver_metrics:
            driver_metrics[dname] = {
                "days_operated": set(), "routes": 0, "packages_loaded": 0,
                "delivered": 0, "failed": 0, "km_total": 0
            }
        dm = driver_metrics[dname]
        dm["days_operated"].add(j.get("date", ""))
        dm["routes"] += 1
        dm["packages_loaded"] += j.get("packages_total", 0)
        dm["delivered"] += j.get("packages_delivered", 0)
        dm["failed"] += j.get("packages_failed", 0)
        dm["km_total"] += (j.get("close_data") or {}).get("km_traveled", 0)
    
    for dname in driver_metrics:
        dm = driver_metrics[dname]
        dm["days_operated"] = len(dm["days_operated"])
        dm["retry"] = dm["packages_loaded"] - dm["delivered"] - dm["failed"]
        dm["delivery_rate"] = round((dm["delivered"] / dm["packages_loaded"] * 100) if dm["packages_loaded"] > 0 else 0, 2)
    
    # Incidents breakdown
    incidents_by_type = {}
    incidents_by_imputability = {"ME / Mensajero": 0, "Cliente (destinatario)": 0, "Por definir": 0}
    for inc in incidents:
        itype = inc.get("incident_type", "Otro")
        incidents_by_type[itype] = incidents_by_type.get(itype, 0) + 1
        imp = inc.get("imputability", "Por definir")
        incidents_by_imputability[imp] = incidents_by_imputability.get(imp, 0) + 1
    
    report_data["provider_metrics"] = provider_metrics
    report_data["driver_metrics"] = driver_metrics
    report_data["incidents_by_type"] = incidents_by_type
    report_data["incidents_by_imputability"] = incidents_by_imputability
    
    # Generate AI insights
    ai_insights = ""
    try:
        llm_key = os.environ.get("EMERGENT_LLM_KEY", "")
        if llm_key:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            
            chat = LlmChat(
                api_key=llm_key,
                session_id=f"report-{uuid.uuid4()}",
                system_message="Eres un analista de operaciones logísticas de última milla. Genera insights concisos y accionables en español. Usa datos duros. Máximo 400 palabras."
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            
            prompt = f"""Analiza estos datos de operación de última milla y genera insights clave:

PERÍODO: {data.date_from} a {data.date_to}
RESUMEN GENERAL: {report_data['total_journeys']} rutas, {report_data['total_packages']} paquetes, tasa de entrega {report_data['delivery_rate']}%, {report_data['total_km']} km, {report_data['total_incidents']} incidencias

POR PROVEEDOR: {str({k: {kk: vv for kk, vv in v.items()} for k, v in provider_metrics.items()})}

POR DRIVER: {str({k: {kk: vv for kk, vv in v.items()} for k, v in driver_metrics.items()})}

INCIDENCIAS POR TIPO: {str(incidents_by_type)}
INCIDENCIAS POR IMPUTABILIDAD: {str(incidents_by_imputability)}

Genera un análisis ejecutivo con: 1) Resumen general, 2) Hallazgos clave, 3) Recomendaciones de mejora."""

            msg = UserMessage(text=prompt)
            ai_insights = await chat.send_message(msg)
    except Exception as e:
        logger.error(f"Error generating AI insights: {e}")
        ai_insights = "No se pudieron generar insights de IA en este momento."
    
    report_data["ai_insights"] = ai_insights
    
    return report_data

@api_router.post("/reports/generate-excel")
async def generate_report_excel(
    data: ReportRequest,
    user: dict = Depends(get_current_user)
):
    """Generate Excel report"""
    from fastapi.responses import Response as FastResponse
    
    j_query = {"date": {"$gte": data.date_from, "$lte": data.date_to}}
    j_query = apply_assignment_filter(user, j_query)
    
    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    journey_ids = [j["id"] for j in journeys]
    
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers_map = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    incidents = await db.incidents.find({"journey_id": {"$in": journey_ids}}, {"_id": 0}).to_list(10000)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet 1: Routes
        routes_data = []
        for j in journeys:
            cd = j.get("close_data") or {}
            sd = j.get("start_data") or {}
            routes_data.append({
                "Fecha": j.get("date", ""),
                "Cliente": clients.get(j.get("client_id"), ""),
                "Proveedor": providers_map.get(j.get("provider_id"), ""),
                "Driver": j.get("driver_name", ""),
                "Tipo Ruta": j.get("route_type", "CDMX / Zona Metro"),
                "Ciudad": j.get("city", ""),
                "Estado": j.get("status", ""),
                "Paquetes Total": j.get("packages_total", 0),
                "Entregados": j.get("packages_delivered", 0),
                "Fallidos": j.get("packages_failed", 0),
                "Reintento": j.get("packages_total", 0) - j.get("packages_delivered", 0) - j.get("packages_failed", 0),
                "Tasa Entrega %": cd.get("delivery_rate", 0),
                "Km": cd.get("km_traveled", 0),
                "Hora Inicio": sd.get("departure_time", ""),
                "Hora Cierre": cd.get("closed_at", ""),
            })
        pd.DataFrame(routes_data).to_excel(writer, sheet_name="Rutas", index=False)
        
        # Sheet 2: Incidents
        inc_data = []
        j_map = {j["id"]: j for j in journeys}
        for inc in incidents:
            j = j_map.get(inc.get("journey_id"), {})
            inc_data.append({
                "Fecha Ruta": j.get("date", ""),
                "Proveedor": providers_map.get(j.get("provider_id"), ""),
                "Driver": j.get("driver_name", ""),
                "Tipo": inc.get("incident_type", ""),
                "Severidad": inc.get("severity", ""),
                "Imputabilidad": inc.get("imputability", "Por definir"),
                "Descripción": inc.get("description", ""),
                "Estado": inc.get("status", ""),
            })
        pd.DataFrame(inc_data).to_excel(writer, sheet_name="Incidencias", index=False)
        
        # Sheet 3: Provider Summary
        prov_summary = {}
        for j in journeys:
            pname = providers_map.get(j.get("provider_id"), "")
            if pname not in prov_summary:
                prov_summary[pname] = {"days": set(), "routes": 0, "loaded": 0, "delivered": 0, "failed": 0, "km": 0}
            ps = prov_summary[pname]
            ps["days"].add(j.get("date", ""))
            ps["routes"] += 1
            ps["loaded"] += j.get("packages_total", 0)
            ps["delivered"] += j.get("packages_delivered", 0)
            ps["failed"] += j.get("packages_failed", 0)
            ps["km"] += (j.get("close_data") or {}).get("km_traveled", 0)
        
        prov_rows = []
        for pname, ps in prov_summary.items():
            prov_rows.append({
                "Proveedor": pname,
                "Días Operados": len(ps["days"]),
                "Total Rutas": ps["routes"],
                "Paquetes Cargados": ps["loaded"],
                "Entregados": ps["delivered"],
                "Fallidos": ps["failed"],
                "Reintentos": ps["loaded"] - ps["delivered"] - ps["failed"],
                "Tasa Entrega %": round((ps["delivered"] / ps["loaded"] * 100) if ps["loaded"] > 0 else 0, 2),
                "Km Totales": ps["km"],
            })
        pd.DataFrame(prov_rows).to_excel(writer, sheet_name="Resumen Proveedores", index=False)
    
    output.seek(0)
    filename = f"reporte_{data.date_from}_{data.date_to}.xlsx"
    return FastResponse(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ==================== QUALITY REPORTS ====================

@api_router.get("/reports/quality")
async def get_quality_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    provider_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Quality report data for evidence scoring analysis."""
    if not date_from:
        d = datetime.now(timezone.utc)
        date_from = (d - timedelta(days=6)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    journey_query = {"date": {"$gte": date_from, "$lte": date_to}, "status": "closed"}
    journey_query = apply_assignment_filter(user, journey_query)
    if provider_id:
        journey_query["provider_id"] = provider_id

    journeys = await db.journeys.find(journey_query, {"_id": 0}).to_list(1000)
    journey_ids = [j["id"] for j in journeys]

    if not journey_ids:
        return {
            "by_provider": [],
            "by_type": [],
            "worst_packages": [],
            "summary": {"avg_score": 0, "total_evaluated": 0, "complete": 0, "partial": 0, "incomplete": 0},
        }

    # Get scored packages
    packages = await db.packages.find(
        {"journey_id": {"$in": journey_ids}, "evidence_score": {"$ne": None}},
        {"_id": 0}
    ).to_list(50000)

    # Build provider lookup
    providers_data = {}
    for j in journeys:
        pid = j.get("provider_id", "unknown")
        pname = j.get("provider_name", pid)
        if pid not in providers_data:
            providers_data[pid] = {"name": pname, "routes": 0, "packages": [], "days": set()}
        providers_data[pid]["routes"] += 1
        providers_data[pid]["days"].add(j["date"])

    # Assign packages to providers via journey
    journey_provider_map = {j["id"]: j.get("provider_id", "unknown") for j in journeys}
    for pkg in packages:
        pid = journey_provider_map.get(pkg.get("journey_id"), "unknown")
        if pid in providers_data:
            providers_data[pid]["packages"].append(pkg)

    by_provider = []
    for pid, pd_data in providers_data.items():
        pkgs = pd_data["packages"]
        delivered_pkgs = [p for p in pkgs if p.get("evidence_type") in ("exitosa", "terceros")]
        scores = [p["evidence_score"] for p in pkgs]
        complete = sum(1 for s in scores if s == 100)
        partial = sum(1 for s in scores if 60 <= s < 100)
        incomplete = sum(1 for s in scores if s < 60)
        avg = round(sum(scores) / len(scores), 1) if scores else 0

        by_provider.append({
            "provider_id": pid,
            "provider_name": pd_data["name"],
            "routes": pd_data["routes"],
            "delivered": len(delivered_pkgs),
            "complete_pct": round(complete / len(scores) * 100, 1) if scores else 0,
            "partial_pct": round(partial / len(scores) * 100, 1) if scores else 0,
            "incomplete_pct": round(incomplete / len(scores) * 100, 1) if scores else 0,
            "avg_score": avg,
        })

    # By evidence type
    type_map = {}
    for pkg in packages:
        et = pkg.get("evidence_type", "desconocido")
        if et not in type_map:
            type_map[et] = {"count": 0, "scores": [], "perfect": 0}
        type_map[et]["count"] += 1
        type_map[et]["scores"].append(pkg["evidence_score"])
        if pkg["evidence_score"] == 100:
            type_map[et]["perfect"] += 1

    by_type = []
    for et, data in type_map.items():
        by_type.append({
            "type": et,
            "count": data["count"],
            "perfect_pct": round(data["perfect"] / data["count"] * 100, 1) if data["count"] else 0,
            "avg_score": round(sum(data["scores"]) / len(data["scores"]), 1) if data["scores"] else 0,
        })

    # Worst 5 packages
    worst = sorted(packages, key=lambda p: p.get("evidence_score", 999))[:5]
    worst_packages = []
    for pkg in worst:
        pid = journey_provider_map.get(pkg.get("journey_id"), "unknown")
        pname = providers_data.get(pid, {}).get("name", pid)
        worst_packages.append({
            "tracking_number": pkg.get("tracking_number") or pkg.get("order_reference_id"),
            "provider_name": pname,
            "score": pkg["evidence_score"],
            "missing": pkg.get("evidence_detail", {}).get("missing_items", []),
            "tracking_url": pkg.get("tracking_url"),
        })

    # Summary
    all_scores = [p["evidence_score"] for p in packages]
    summary = {
        "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else 0,
        "total_evaluated": len(all_scores),
        "complete": sum(1 for s in all_scores if s == 100),
        "partial": sum(1 for s in all_scores if 60 <= s < 100),
        "incomplete": sum(1 for s in all_scores if s < 60),
    }

    return {
        "by_provider": by_provider,
        "by_type": by_type,
        "worst_packages": worst_packages,
        "summary": summary,
    }


@api_router.post("/reports/quality-export")
async def export_quality_report(
    date_from: str = Form(...),
    date_to: str = Form(...),
    provider_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    """Export Cubbo quality report as Excel (only packages with score < 100)."""
    import io
    from fastapi.responses import Response as FastResponse
    
    journey_query = {"date": {"$gte": date_from, "$lte": date_to}, "status": "closed"}
    journey_query = apply_assignment_filter(user, journey_query)
    if provider_id:
        journey_query["provider_id"] = provider_id

    journeys = await db.journeys.find(journey_query, {"_id": 0}).to_list(1000)
    journey_map = {j["id"]: j for j in journeys}
    journey_ids = list(journey_map.keys())

    packages = await db.packages.find(
        {"journey_id": {"$in": journey_ids}, "evidence_score": {"$ne": None, "$lt": 100}},
        {"_id": 0}
    ).to_list(50000)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        rows = []
        for pkg in packages:
            j = journey_map.get(pkg.get("journey_id"), {})
            rows.append({
                "Fecha": j.get("date", ""),
                "Guía": pkg.get("tracking_number") or pkg.get("order_reference_id", ""),
                "Proveedor": j.get("provider_name", ""),
                "Tipo de entrega": pkg.get("evidence_type", ""),
                "Score": pkg.get("evidence_score", 0),
                "Evidencias faltantes": ", ".join(pkg.get("evidence_detail", {}).get("missing_items", [])),
                "Fotos": pkg.get("kosmo_proof_count", 0),
                "Nota del mensajero": pkg.get("kosmo_driver_note", ""),
            })
        pd.DataFrame(rows).to_excel(writer, sheet_name="Calidad de soporte", index=False)

    output.seek(0)
    filename = f"calidad_cubbo_{date_from}_{date_to}.xlsx"
    return FastResponse(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.post("/reports/evaluate-journey/{journey_id}")
async def evaluate_journey_quality(
    journey_id: str,
    user: dict = Depends(get_current_user)
):
    """Manually trigger evidence quality evaluation for a journey."""
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    await evaluate_packages_for_journey(db, journey_id)
    
    # Get updated packages with scores
    packages = await db.packages.find(
        {"journey_id": journey_id, "evidence_score": {"$ne": None}},
        {"_id": 0, "evidence_score": 1}
    ).to_list(5000)
    
    scores = [p["evidence_score"] for p in packages]
    return {
        "evaluated": len(scores),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "complete": sum(1 for s in scores if s == 100),
        "partial": sum(1 for s in scores if 60 <= s < 100),
        "incomplete": sum(1 for s in scores if s < 60),
    }


@api_router.post("/journeys/{journey_id}/packages/{guide}/evaluate-evidence")
async def evaluate_package_evidence(
    journey_id: str,
    guide: str,
    user: dict = Depends(get_current_user),
):
    """AI-powered evidence evaluation for a single package."""
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    result = await evaluate_single_package_for_journey(db, journey_id, guide, use_ai=True)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@api_router.post("/journeys/{journey_id}/evaluate-evidence-all")
async def evaluate_all_evidence(
    journey_id: str,
    user: dict = Depends(get_current_user),
):
    """AI-powered evidence evaluation for all packages in a journey."""
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    # Use AI for evaluation
    await evaluate_packages_for_journey(db, journey_id, use_ai=True)

    # Return updated stats
    packages = await db.packages.find(
        {"journey_id": journey_id, "evidence_score": {"$ne": None}},
        {"_id": 0, "evidence_score": 1, "evidence_method": 1},
    ).to_list(5000)

    scores = [p["evidence_score"] for p in packages]
    ai_count = sum(1 for p in packages if p.get("evidence_method") == "ai")
    return {
        "evaluated": len(scores),
        "ai_evaluated": ai_count,
        "rules_evaluated": len(scores) - ai_count,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "complete": sum(1 for s in scores if s == 100),
        "partial": sum(1 for s in scores if 60 <= s < 100),
        "incomplete": sum(1 for s in scores if s < 60),
    }


# ==================== ROOT ====================

@api_router.get("/")
async def root():
    return {"message": "LastMile OS API v1.0", "status": "running"}

@api_router.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# ==================== ANALYTICS ====================

@api_router.get("/analytics/heatmap")
async def get_heatmap_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "address_cp",  # address_cp, address_municipio, address_estado
    user: dict = Depends(get_current_user),
):
    """Geographic heatmap: group packages by CP, municipio, or estado."""
    # Get journey IDs in date range
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    j_query = apply_assignment_filter(user, j_query)

    journeys = await db.journeys.find(j_query, {"_id": 0, "id": 1}).to_list(500)
    journey_ids = [j["id"] for j in journeys]

    if not journey_ids:
        return {"group_by": group_by, "total_packages": 0, "areas": []}

    # Validate group_by
    if group_by not in ("address_cp", "address_municipio", "address_estado", "zone"):
        group_by = "address_cp"

    pipeline = [
        {"$match": {"journey_id": {"$in": journey_ids}, group_by: {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": f"${group_by}",
            "total": {"$sum": 1},
            "delivered": {"$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
        {"$limit": 100},
    ]

    results = await db.packages.aggregate(pipeline).to_list(100)

    areas = []
    for r in results:
        area_name = r["_id"] or "Sin dato"
        total = r["total"]
        delivered = r["delivered"]
        rate = round(delivered / total * 100, 1) if total > 0 else 0
        areas.append({
            "area": area_name,
            "total": total,
            "delivered": delivered,
            "failed": r["failed"],
            "pending": r["pending"],
            "delivery_rate": rate,
        })

    total_pkgs = sum(a["total"] for a in areas)
    return {"group_by": group_by, "total_packages": total_pkgs, "areas": areas}


@api_router.post("/analytics/heatmap-export")
async def export_heatmap_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "address_cp",
    user: dict = Depends(get_current_user),
):
    """Export heatmap data as Excel."""
    data = await get_heatmap_data(date_from, date_to, group_by, user)

    rows = []
    for a in data["areas"]:
        rows.append({
            "Área": a["area"],
            "Total paquetes": a["total"],
            "Entregados": a["delivered"],
            "Fallidos": a["failed"],
            "Pendientes": a["pending"],
            "Tasa de entrega %": a["delivery_rate"],
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Heatmap")
    output.seek(0)

    from starlette.responses import StreamingResponse
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=heatmap_{group_by}.xlsx"},
    )


# ==================== REPORTING API (For Power BI, Tableau, etc.) ====================

@api_router.get("/reports/journeys")
async def report_journeys(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Get journeys data for reporting/BI tools.
    Returns flattened data suitable for Power BI, Tableau, etc.
    """
    query = {}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})["$lte"] = date_to
    if client_id:
        query["client_id"] = client_id
    if provider_id:
        query["provider_id"] = provider_id
    if status:
        query["status"] = status
    
    journeys = await db.journeys.find(query, {"_id": 0}).to_list(10000)
    
    # Enrich with names
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    # Flatten for BI tools
    result = []
    for j in journeys:
        close_data = j.get("close_data") or {}
        start_data = j.get("start_data") or {}
        
        # Count incidents
        incidents_count = await db.incidents.count_documents({"journey_id": j["id"]})
        open_incidents = await db.incidents.count_documents({"journey_id": j["id"], "status": "open"})
        
        result.append({
            "journey_id": j["id"],
            "date": j.get("date"),
            "client_id": j.get("client_id"),
            "client_name": clients.get(j.get("client_id"), ""),
            "provider_id": j.get("provider_id"),
            "provider_name": providers.get(j.get("provider_id"), ""),
            "driver_name": j.get("driver_name", ""),
            "status": j.get("status"),
            "route_type": j.get("route_type", "CDMX / Zona Metro"),
            "city": j.get("city", ""),
            "packages_total": j.get("packages_total", 0),
            "packages_delivered": j.get("packages_delivered", 0),
            "packages_failed": j.get("packages_failed", 0),
            "packages_retry": j.get("packages_retry", 0),
            "delivery_rate": close_data.get("delivery_rate", 0),
            "km_traveled": close_data.get("km_traveled", 0),
            "odometer_start": start_data.get("odometer_start", 0),
            "odometer_end": close_data.get("odometer_end", 0),
            "departure_time": start_data.get("departure_time"),
            "closed_at": close_data.get("closed_at"),
            "fuel_level": start_data.get("fuel_level", ""),
            "incidents_total": incidents_count,
            "incidents_open": open_incidents,
            "created_at": j.get("created_at")
        })
    
    return {"data": result, "total": len(result)}

@api_router.get("/reports/packages")
async def report_packages(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    journey_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Get packages data for reporting/BI tools.
    """
    # Build journey filter
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    
    if journey_id:
        journey_ids = [journey_id]
    else:
        journeys = await db.journeys.find(j_query, {"id": 1, "_id": 0}).to_list(10000)
        journey_ids = [j["id"] for j in journeys]
    
    # Build package query
    pkg_query = {"journey_id": {"$in": journey_ids}}
    if status:
        pkg_query["status"] = status
    
    packages = await db.packages.find(pkg_query, {"_id": 0}).to_list(50000)
    
    # Enrich with journey data
    journeys_map = {}
    for jid in journey_ids:
        j = await db.journeys.find_one({"id": jid}, {"_id": 0})
        if j:
            journeys_map[jid] = j
    
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    result = []
    for pkg in packages:
        journey = journeys_map.get(pkg.get("journey_id"), {})
        result.append({
            "package_id": pkg.get("id"),
            "journey_id": pkg.get("journey_id"),
            "cosmo_route_id": pkg.get("cosmo_route_id", ""),
            "journey_date": journey.get("date"),
            "tracking_number": pkg.get("tracking_number") or pkg.get("order_reference_id"),
            "tracking_url": pkg.get("tracking_url", ""),
            "recipient_name": pkg.get("recipient_name"),
            "address": pkg.get("address"),
            "zone": pkg.get("zone"),
            "status": pkg.get("status"),
            "cosmo_status": pkg.get("cosmo_status", ""),
            "failure_reason": pkg.get("failure_reason", ""),
            "delivery_attempt": pkg.get("delivery_attempt", 1),
            "evidence_score": pkg.get("evidence_score"),
            "evidence_type": pkg.get("evidence_type"),
            "kosmo_proof_count": pkg.get("kosmo_proof_count", 0),
            "reviewed_by": pkg.get("reviewed_by"),
            "reviewed_at": pkg.get("reviewed_at"),
            "client_name": clients.get(journey.get("client_id"), ""),
            "provider_name": providers.get(journey.get("provider_id"), ""),
            "driver_name": journey.get("driver_name", "")
        })
    
    return {"data": result, "total": len(result)}

@api_router.get("/reports/incidents")
async def report_incidents(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    incident_type: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Get incidents data for reporting/BI tools.
    """
    # Get journeys in date range
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    
    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    journey_ids = [j["id"] for j in journeys]
    journeys_map = {j["id"]: j for j in journeys}
    
    # Build incident query
    inc_query = {"journey_id": {"$in": journey_ids}}
    if severity:
        inc_query["severity"] = severity
    if status:
        inc_query["status"] = status
    if incident_type:
        inc_query["incident_type"] = incident_type
    
    incidents = await db.incidents.find(inc_query, {"_id": 0}).to_list(10000)
    
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    result = []
    for inc in incidents:
        journey = journeys_map.get(inc.get("journey_id"), {})
        result.append({
            "incident_id": inc.get("id"),
            "journey_id": inc.get("journey_id"),
            "journey_date": journey.get("date"),
            "occurred_at": inc.get("occurred_at"),
            "incident_type": inc.get("incident_type"),
            "description": inc.get("description"),
            "severity": inc.get("severity"),
            "imputability": inc.get("imputability", "Por definir"),
            "status": inc.get("status"),
            "tracking_number": inc.get("tracking_number", ""),
            "action_taken": inc.get("action_taken", ""),
            "resolved_at": inc.get("resolved_at"),
            "client_name": clients.get(journey.get("client_id"), ""),
            "provider_name": providers.get(journey.get("provider_id"), ""),
            "driver_name": journey.get("driver_name", ""),
            "created_at": inc.get("created_at")
        })
    
    return {"data": result, "total": len(result)}

@api_router.get("/reports/kpis")
async def report_kpis(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "day",  # day, week, month, provider, client
    user: dict = Depends(get_current_user)
):
    """
    Get aggregated KPIs for reporting/BI tools.
    """
    if not date_from:
        date_from = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    journeys = await db.journeys.find(
        {"date": {"$gte": date_from, "$lte": date_to}},
        {"_id": 0}
    ).to_list(10000)
    
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    # Group data
    groups = {}
    for j in journeys:
        if group_by == "provider":
            key = providers.get(j.get("provider_id"), "Sin proveedor")
        elif group_by == "client":
            key = clients.get(j.get("client_id"), "Sin cliente")
        elif group_by == "week":
            d = datetime.strptime(j.get("date", date_from), "%Y-%m-%d")
            key = f"{d.year}-W{d.isocalendar()[1]:02d}"
        elif group_by == "month":
            key = j.get("date", "")[:7]  # YYYY-MM
        else:  # day
            key = j.get("date", "")
        
        if key not in groups:
            groups[key] = {
                "group": key,
                "journeys_count": 0,
                "journeys_completed": 0,
                "packages_total": 0,
                "packages_delivered": 0,
                "packages_failed": 0,
                "km_total": 0,
                "incidents_count": 0
            }
        
        close_data = j.get("close_data") or {}
        groups[key]["journeys_count"] += 1
        if j.get("status") == "closed":
            groups[key]["journeys_completed"] += 1
        groups[key]["packages_total"] += j.get("packages_total", 0)
        groups[key]["packages_delivered"] += j.get("packages_delivered", 0)
        groups[key]["packages_failed"] += j.get("packages_failed", 0)
        groups[key]["km_total"] += close_data.get("km_traveled", 0)
    
    # Calculate delivery rates
    result = []
    for key, data in groups.items():
        data["delivery_rate"] = round(
            (data["packages_delivered"] / data["packages_total"] * 100) 
            if data["packages_total"] > 0 else 0, 2
        )
        result.append(data)
    
    # Sort by group
    result.sort(key=lambda x: x["group"])
    
    return {"data": result, "total": len(result), "date_from": date_from, "date_to": date_to}

@api_router.get("/reports/schema")
async def report_schema():
    """
    Returns the schema of available report endpoints for BI tool integration.
    """
    return {
        "api_version": "1.0",
        "endpoints": [
            {
                "name": "Journeys Report",
                "endpoint": "/api/reports/journeys",
                "method": "GET",
                "description": "Datos de rutas con métricas de entrega",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "client_id", "type": "string", "required": False},
                    {"name": "provider_id", "type": "string", "required": False},
                    {"name": "status", "type": "string", "enum": ["scheduled", "in_progress", "closed"], "required": False}
                ],
                "fields": [
                    "journey_id", "date", "client_id", "client_name", "provider_id", "provider_name",
                    "driver_name", "status", "packages_total", "packages_delivered", "packages_failed",
                    "delivery_rate", "km_traveled", "incidents_total", "incidents_open"
                ]
            },
            {
                "name": "Packages Report",
                "endpoint": "/api/reports/packages",
                "method": "GET",
                "description": "Datos detallados de paquetes",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "status", "type": "string", "enum": ["pending", "delivered", "failed", "returned"], "required": False},
                    {"name": "journey_id", "type": "string", "required": False}
                ],
                "fields": [
                    "package_id", "journey_id", "cosmo_route_id", "journey_date", "tracking_number", "tracking_url",
                    "recipient_name", "address", "zone", "status", "failure_reason", "delivery_attempt",
                    "evidence_score", "evidence_type", "kosmo_proof_count", "kosmo_proof_urls",
                    "reviewed_by", "reviewed_at",
                    "client_name", "provider_name", "driver_name"
                ]
            },
            {
                "name": "Incidents Report",
                "endpoint": "/api/reports/incidents",
                "method": "GET",
                "description": "Datos de incidencias",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "severity", "type": "string", "enum": ["Alto", "Medio", "Bajo"], "required": False},
                    {"name": "status", "type": "string", "enum": ["open", "resolved"], "required": False},
                    {"name": "incident_type", "type": "string", "required": False}
                ],
                "fields": [
                    "incident_id", "journey_id", "journey_date", "occurred_at", "incident_type",
                    "description", "severity", "status", "action_taken", "resolved_at",
                    "client_name", "provider_name", "driver_name"
                ]
            },
            {
                "name": "KPIs Report",
                "endpoint": "/api/reports/kpis",
                "method": "GET",
                "description": "KPIs agregados por período o dimensión",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "group_by", "type": "string", "enum": ["day", "week", "month", "provider", "client"], "default": "day"}
                ],
                "fields": [
                    "group", "journeys_count", "journeys_completed", "packages_total",
                    "packages_delivered", "packages_failed", "km_total", "delivery_rate"
                ]
            },
            {
                "name": "Custom Report (AI)",
                "endpoint": "/api/reports/generate",
                "method": "POST",
                "description": "Genera reporte personalizable con insights de IA (Claude)",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "sections", "type": "array", "enum": ["provider_metrics", "driver_metrics", "incidents_breakdown"], "required": False}
                ],
                "fields": [
                    "total_journeys", "total_packages", "total_delivered", "total_failed",
                    "delivery_rate", "provider_metrics", "driver_metrics", "incidents_by_type",
                    "incidents_by_imputability", "ai_insights"
                ]
            },
            {
                "name": "Report Excel Export",
                "endpoint": "/api/reports/generate-excel",
                "method": "POST",
                "description": "Descarga reporte en formato Excel con hojas de rutas, incidencias y resumen por proveedor",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": True}
                ],
                "fields": ["Archivo .xlsx con 3 hojas: Rutas, Incidencias, Resumen Proveedores"]
            },
            {
                "name": "Kosmo Tracking Sync",
                "endpoint": "/api/sync/tracking",
                "method": "POST",
                "description": "Sincroniza estatus de paquetes scrapeando páginas públicas de Kosmo. Máx 250 por llamada. Responde inmediatamente, ejecuta en segundo plano.",
                "parameters": [],
                "fields": ["status", "message"]
            },
            {
                "name": "Kosmo Sync Status",
                "endpoint": "/api/sync/status",
                "method": "GET",
                "description": "Timestamp y stats de la última sincronización de Kosmo.",
                "parameters": [],
                "fields": ["last_sync", "total_checked", "updated", "errors"]
            },
            {
                "name": "Quality Report",
                "endpoint": "/api/reports/quality",
                "method": "GET",
                "description": "Reporte de calidad de soporte basado en estándar Cubbo (3 fotos por entrega).",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "provider_id", "type": "string", "required": False}
                ],
                "fields": [
                    "by_provider[]", "by_type[]", "worst_packages[]",
                    "summary.avg_score", "summary.complete", "summary.partial", "summary.incomplete"
                ]
            },
            {
                "name": "Quality Excel Export (Cubbo)",
                "endpoint": "/api/reports/quality-export",
                "method": "POST",
                "description": "Exporta Excel para Cubbo con paquetes que tienen score < 100.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "provider_id", "type": "string", "required": False}
                ],
                "fields": ["Archivo .xlsx: fecha, guía, proveedor, tipo entrega, score, evidencias faltantes"]
            },
            {
                "name": "Package Search",
                "endpoint": "/api/packages/search",
                "method": "GET",
                "description": "Busca paquetes por guía o referencia (order_reference_id).",
                "parameters": [
                    {"name": "q", "type": "string", "required": True}
                ],
                "fields": [
                    "id", "tracking_number", "order_reference_id", "recipient_name",
                    "status", "journey_id", "journey_date", "provider_name"
                ]
            },
            {
                "name": "Cleanup Routes & Packages",
                "endpoint": "/api/cleanup/routes-packages",
                "method": "POST",
                "description": "Elimina todas las rutas, paquetes e incidencias. Solo coordinator/developer. Requiere confirmación en UI.",
                "parameters": [],
                "fields": ["deleted.journeys", "deleted.packages", "deleted.incidents"]
            },
            {
                "name": "Resolve All Incidents",
                "endpoint": "/api/incidents/journey/{journey_id}/resolve-all",
                "method": "PUT",
                "description": "Marca todas las incidencias abiertas de una ruta como resueltas en lote.",
                "parameters": [
                    {"name": "journey_id", "type": "string", "required": True}
                ],
                "fields": ["resolved_count", "message"]
            },
            {
                "name": "Review Package",
                "endpoint": "/api/packages/{package_id}/review",
                "method": "PUT",
                "description": "Marca un paquete como revisado por el usuario actual.",
                "parameters": [
                    {"name": "package_id", "type": "string", "required": True}
                ],
                "fields": ["reviewed_by", "reviewed_at", "message"]
            }
        ],
        "authentication": {
            "type": "Bearer Token",
            "header": "Authorization",
            "format": "Bearer <token>",
            "obtain_token": "POST /api/auth/login with {email, password}"
        }
    }

# Include the router
app.include_router(api_router)

# Create and include system routes with proper dependency injection
system_router = create_system_router(db, get_current_user)
api_system_router = APIRouter(prefix="/api")
api_system_router.include_router(system_router)
app.include_router(api_system_router)

# Create and include Kosmo sync routes
kosmo_router = create_kosmo_router(db, get_current_user)
api_kosmo_router = APIRouter(prefix="/api")
api_kosmo_router.include_router(kosmo_router)
app.include_router(api_kosmo_router)

# Add audit middleware (must be after CORS)
app.add_middleware(AuditMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Create indexes for composite unique key
    await db.packages.create_index(
        [("cosmo_route_id", 1), ("order_reference_id", 1)],
        unique=False,
        background=True
    )
    await db.packages.create_index("order_reference_id", background=True)
    start_periodic_sync(db)

@app.on_event("shutdown")
async def shutdown_db_client():
    stop_periodic_sync()
    client.close()
