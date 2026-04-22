"""
User, Client, and Provider management routes.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime, timezone

from dependencies import db, get_current_user, require_role
from models import (
    UserCreate, ClientBase, ClientResponse,
    ProviderBase, ProviderResponse,
)
from dependencies import hash_password

router = APIRouter(tags=["Users"])


# ==================== USER MANAGEMENT ====================

@router.get("/users")
async def get_users(user: dict = Depends(require_role(["coordinator", "developer"]))):
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(100)
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    for u in users:
        assigned_clients = u.get("assigned_clients", [])
        assigned_providers = u.get("assigned_providers", [])
        u["assigned_client_names"] = [clients.get(cid, "") for cid in assigned_clients if cid in clients]
        u["assigned_provider_names"] = [providers.get(pid, "") for pid in assigned_providers if pid in providers]
    return users


@router.post("/users")
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(new_user)
    return {k: v for k, v in new_user.items() if k not in ["_id", "password"]}


@router.put("/users/{user_id}")
async def update_user(user_id: str, data: dict, admin: dict = Depends(require_role(["coordinator", "developer"]))):
    update_data = {k: v for k, v in data.items() if k not in ["id", "password", "_id"]}
    if not update_data:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")
    result = await db.users.update_one({"id": user_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Usuario actualizado"}


@router.put("/users/{user_id}/assignments")
async def update_user_assignments(
    user_id: str,
    data: dict,
    admin: dict = Depends(require_role(["coordinator", "developer"])),
):
    update_data = {}
    if "assigned_clients" in data:
        update_data["assigned_clients"] = data["assigned_clients"]
    if "assigned_providers" in data:
        update_data["assigned_providers"] = data["assigned_providers"]
    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")
    result = await db.users.update_one({"id": user_id}, {"$set": update_data})
    if result.modified_count == 0:
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Asignaciones actualizadas"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Usuario eliminado"}


# ==================== CLIENTS ====================

@router.get("/clients", response_model=List[ClientResponse])
async def get_clients(user: dict = Depends(get_current_user)):
    clients = await db.clients.find({}, {"_id": 0}).to_list(100)
    return clients


@router.post("/clients", response_model=ClientResponse)
async def create_client(data: ClientBase, user: dict = Depends(require_role(["coordinator", "agent"]))):
    new_client = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.clients.insert_one(new_client)
    return {"id": new_client["id"], "name": new_client["name"]}


@router.put("/clients/{client_id}")
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


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.clients.delete_one({"id": client_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"message": "Cliente eliminado"}


# ==================== PROVIDERS ====================

@router.get("/providers", response_model=List[ProviderResponse])
async def get_providers(user: dict = Depends(get_current_user)):
    providers = await db.providers.find({}, {"_id": 0}).to_list(100)
    return providers


@router.post("/providers", response_model=ProviderResponse)
async def create_provider(data: ProviderBase, user: dict = Depends(require_role(["coordinator", "agent"]))):
    new_provider = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "contact_name": data.contact_name,
        "contact_phone": data.contact_phone,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.providers.insert_one(new_provider)
    return {k: v for k, v in new_provider.items() if k != "_id"}


@router.put("/providers/{provider_id}")
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


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.providers.delete_one({"id": provider_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return {"message": "Proveedor eliminado"}
