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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'lastmile_os')]

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'lastmile-secret-key-2026')
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8

# File upload directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Create the main app
app = FastAPI(title="LastMile OS API")

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
    odometer_start: int
    fuel_level: str
    vehicle_condition: str
    vehicle_notes: Optional[str] = None
    packages_loaded: int
    notes: Optional[str] = None
    checklist_completed: bool

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

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    token = create_token(user["id"], user["email"], user["role"])
    user_response = {k: v for k, v in user.items() if k != "password"}
    return TokenResponse(access_token=token, user=user_response)

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

@api_router.post("/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    return {"message": "Sesión cerrada exitosamente"}

# ==================== USER MANAGEMENT (COORDINATOR ONLY) ====================

@api_router.get("/users")
async def get_users(user: dict = Depends(require_role(["coordinator"]))):
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
async def create_user(data: UserCreate, user: dict = Depends(require_role(["coordinator"]))):
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
async def update_user(user_id: str, data: dict, admin: dict = Depends(require_role(["coordinator"]))):
    update_data = {k: v for k, v in data.items() if k not in ["id", "password", "_id"]}
    result = await db.users.update_one({"id": user_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Usuario actualizado"}

@api_router.put("/users/{user_id}/assignments")
async def update_user_assignments(
    user_id: str, 
    data: dict,
    admin: dict = Depends(require_role(["coordinator"]))
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
async def delete_user(user_id: str, admin: dict = Depends(require_role(["coordinator"]))):
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Usuario eliminado"}

@api_router.post("/users/change-password")
async def change_password_by_admin(data: PasswordChangeByAdmin, admin: dict = Depends(require_role(["coordinator"]))):
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
async def get_password_reset_requests(admin: dict = Depends(require_role(["coordinator"]))):
    requests = await db.password_reset_requests.find({}, {"_id": 0}).sort("requested_at", -1).to_list(100)
    return requests

@api_router.delete("/password-reset-requests/{request_id}")
async def dismiss_password_reset_request(request_id: str, admin: dict = Depends(require_role(["coordinator"]))):
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

# ==================== JOURNEYS ====================

@api_router.get("/journeys")
async def get_journeys(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
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
    
    journeys = await db.journeys.find(query, {"_id": 0}).sort("date", -1).to_list(500)
    
    # Enrich with client and provider names
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    
    for j in journeys:
        j["client_name"] = clients.get(j.get("client_id"), "")
        j["provider_name"] = providers.get(j.get("provider_id"), "")
        # Count incidents
        incidents = await db.incidents.count_documents({"journey_id": j["id"]})
        j["incidents_count"] = incidents
        open_incidents = await db.incidents.count_documents({"journey_id": j["id"], "status": "open"})
        j["open_incidents_count"] = open_incidents
    
    return journeys

@api_router.get("/journeys/{journey_id}")
async def get_journey(journey_id: str, user: dict = Depends(get_current_user)):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    # Get client and provider names
    client = await db.clients.find_one({"id": journey.get("client_id")}, {"_id": 0})
    provider = await db.providers.find_one({"id": journey.get("provider_id")}, {"_id": 0})
    journey["client_name"] = client["name"] if client else ""
    journey["provider_name"] = provider["name"] if provider else ""
    
    # Get packages
    packages = await db.packages.find({"journey_id": journey_id}, {"_id": 0}).to_list(1000)
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
    
    return {"id": journey_id, "message": "Jornada creada exitosamente"}

@api_router.put("/journeys/{journey_id}/start")
async def start_journey(journey_id: str, data: JourneyStartData, user: dict = Depends(require_role(["coordinator", "agent"]))):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    if journey["status"] != "scheduled":
        raise HTTPException(status_code=400, detail="La jornada ya fue iniciada o cerrada")
    
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
        "started_at": datetime.now(timezone.utc).isoformat(),
        "started_by": user["id"]
    }
    
    await db.journeys.update_one(
        {"id": journey_id},
        {"$set": {"status": "in_progress", "start_data": start_data}}
    )
    
    return {"message": "Jornada iniciada exitosamente"}

@api_router.put("/journeys/{journey_id}/close")
async def close_journey(journey_id: str, data: JourneyCloseData, user: dict = Depends(require_role(["coordinator", "agent"]))):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    if journey["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="La jornada debe estar en progreso para cerrarla")
    
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
    
    # Update failed packages
    for failed_pkg in data.failed_packages:
        await db.packages.update_one(
            {"id": failed_pkg["id"]},
            {"$set": {"status": "retry", "failure_reason": failed_pkg.get("failure_reason", "")}}
        )
    
    return {"message": "Jornada cerrada exitosamente", "close_data": close_data}

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
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"]
    }
    await db.incidents.insert_one(incident)
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

@api_router.post("/journeys/from-cosmo")
async def create_journeys_from_cosmo(
    data: CosmoJourneyCreate,
    user: dict = Depends(require_role(["coordinator", "agent"]))
):
    created_journeys = []
    skipped_duplicates = []
    errors = []
    
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
    
    # Get all existing orders to check for duplicates
    existing_orders = await db.packages.find({}, {"order_reference_id": 1, "_id": 0}).to_list(10000)
    existing_order_ids = set(o.get("order_reference_id", "") for o in existing_orders if o.get("order_reference_id"))
    
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
            # Try to get from existing mappings in DB
            existing_mapping = await db.messenger_mappings.find_one({"messenger_name": driver_name}, {"_id": 0})
            if existing_mapping:
                provider_id = existing_mapping.get("provider_id")
        
        if not provider_id:
            errors.append(f"Sin proveedor asignado para mensajero: {driver_name}")
            continue
        
        # Check if journey with this route_id already exists
        existing_journey = await db.journeys.find_one({"cosmo_route_id": route_id}, {"_id": 0})
        if existing_journey:
            skipped_duplicates.append(route_id)
            continue
        
        # Get orders for this route
        route_orders = orders_by_route.get(route_id, [])
        
        # Filter out duplicate orders
        new_orders = []
        duplicate_orders = []
        for order in route_orders:
            order_ref = order.get("order_reference_id", "")
            if order_ref in existing_order_ids:
                duplicate_orders.append(order_ref)
            else:
                new_orders.append(order)
                existing_order_ids.add(order_ref)  # Mark as used
        
        if not new_orders and route_orders:
            skipped_duplicates.append(f"{route_id} (todas las órdenes duplicadas)")
            continue
        
        # Create journey
        journey_id = str(uuid.uuid4())
        journey = {
            "id": journey_id,
            "cosmo_route_id": route_id,
            "date": data.date,
            "client_id": data.client_id,
            "provider_id": provider_id,
            "driver_name": driver_name,
            "team": route.get("team", ""),
            "status": "scheduled",
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
            package = {
                "id": str(uuid.uuid4()),
                "journey_id": journey_id,
                "order_reference_id": order.get("order_reference_id", ""),
                "tracking_number": order.get("order_reference_id", ""),
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
                "is_retry": False
            }
            await db.packages.insert_one(package)
            
            # Update journey counts based on cosmo status
            if package["status"] == "delivered":
                await db.journeys.update_one({"id": journey_id}, {"$inc": {"packages_delivered": 1}})
            elif package["status"] == "failed":
                await db.journeys.update_one({"id": journey_id}, {"$inc": {"packages_failed": 1}})
        
        created_journeys.append({
            "journey_id": journey_id,
            "route_id": route_id,
            "driver": driver_name,
            "packages": len(new_orders),
            "duplicates_skipped": len(duplicate_orders)
        })
    
    return {
        "message": f"{len(created_journeys)} jornadas creadas",
        "created_journeys": created_journeys,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors
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
    user: dict = Depends(get_current_user)
):
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Active journeys today
    active_journeys = await db.journeys.count_documents({
        "date": date,
        "status": "in_progress"
    })
    
    # Closed journeys today
    closed_journeys = await db.journeys.count_documents({
        "date": date,
        "status": "closed"
    })
    
    # Total journeys today
    total_journeys = await db.journeys.count_documents({"date": date})
    
    # Packages stats
    journeys_today = await db.journeys.find({"date": date}, {"_id": 0}).to_list(100)
    total_packages = sum(j.get("packages_total", 0) for j in journeys_today)
    delivered_packages = sum(j.get("packages_delivered", 0) for j in journeys_today)
    
    # Open incidents today
    journey_ids = [j["id"] for j in journeys_today]
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
    
    return {
        "date": date,
        "active_journeys": active_journeys,
        "closed_journeys": closed_journeys,
        "total_journeys": total_journeys,
        "total_packages": total_packages,
        "delivered_packages": delivered_packages,
        "delivery_rate": round(delivery_rate, 2),
        "open_incidents": open_incidents,
        "total_km": total_km
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
    
    # Get journeys in date range
    journeys = await db.journeys.find(
        {"date": {"$gte": date_from, "$lte": date_to}},
        {"_id": 0}
    ).to_list(500)
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
    
    # Get all providers
    providers = await db.providers.find({}, {"_id": 0}).to_list(100)
    
    comparison = []
    for provider in providers:
        journeys = await db.journeys.find(
            {
                "provider_id": provider["id"],
                "date": {"$gte": date_from, "$lte": date_to}
            },
            {"_id": 0}
        ).to_list(500)
        
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
        headers={"Content-Disposition": f"attachment; filename=jornadas_export_{datetime.now().strftime('%Y%m%d')}.xlsx"}
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

# ==================== ROOT ====================

@api_router.get("/")
async def root():
    return {"message": "LastMile OS API v1.0", "status": "running"}

@api_router.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

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
        j_query.setdefault("date", {})["$lte"] = date_to
    
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
            "journey_date": journey.get("date"),
            "tracking_number": pkg.get("tracking_number") or pkg.get("order_reference_id"),
            "tracking_url": pkg.get("tracking_url", ""),
            "recipient_name": pkg.get("recipient_name"),
            "address": pkg.get("address"),
            "zone": pkg.get("zone"),
            "status": pkg.get("status"),
            "cosmo_status": pkg.get("cosmo_status", ""),
            "failure_reason": pkg.get("failure_reason", ""),
            "is_retry": pkg.get("is_retry", False),
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
        j_query.setdefault("date", {})["$lte"] = date_to
    
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
                "description": "Datos de jornadas con métricas de entrega",
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
                    {"name": "status", "type": "string", "enum": ["pending", "delivered", "failed", "retry"], "required": False},
                    {"name": "journey_id", "type": "string", "required": False}
                ],
                "fields": [
                    "package_id", "journey_id", "journey_date", "tracking_number", "tracking_url",
                    "recipient_name", "address", "zone", "status", "failure_reason", "is_retry",
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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
