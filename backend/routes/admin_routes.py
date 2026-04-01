"""
Admin routes: seed data, cleanup, upload history.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta

from dependencies import db, get_current_user, require_role, hash_password

router = APIRouter(tags=["Admin"])


# ==================== UPLOAD HISTORY ====================

@router.get("/upload-history")
async def get_upload_history(user: dict = Depends(get_current_user)):
    history = await db.upload_history.find({}, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    for h in history:
        h["client_name"] = clients.get(h.get("client_id"), "")
        h["provider_name"] = providers.get(h.get("provider_id"), "")
    return history


@router.post("/upload-history")
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
        "uploaded_by": user["id"],
    }
    await db.upload_history.insert_one(history_entry)
    return history_entry


# ==================== SEED DATA ====================

@router.post("/seed")
async def seed_database():
    existing_users = await db.users.count_documents({})
    if existing_users > 0:
        return {"message": "Base de datos ya tiene datos"}

    clients = [
        {"id": str(uuid.uuid4()), "name": "Cubbo", "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Grupo Nadro", "created_at": datetime.now(timezone.utc).isoformat()},
    ]
    await db.clients.insert_many(clients)

    providers = [
        {
            "id": str(uuid.uuid4()),
            "name": "Chamedé Logistics",
            "contact_name": "Chamedé",
            "contact_phone": "+52 55 0000 0001",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Octavio Transport",
            "contact_name": "Octavio",
            "contact_phone": "+52 55 0000 0002",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    await db.providers.insert_many(providers)

    password_hash = hash_password("LastMile2026")
    users = [
        {"id": str(uuid.uuid4()), "email": "agente@me.mx", "name": "Agente ME", "role": "agent", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "yael@me.mx", "name": "Yael Coordinador", "role": "coordinator", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "karina@me.mx", "name": "Karina Ejecutivo", "role": "executive", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "dev@me.mx", "name": "Dev Admin", "role": "developer", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "proveedor@me.mx", "name": "Proveedor Chamedé", "role": "proveedor", "password": password_hash, "assigned_providers": [providers[0]["id"]], "created_at": datetime.now(timezone.utc).isoformat()},
    ]
    await db.users.insert_many(users)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    journey1_id = str(uuid.uuid4())
    journey1 = {
        "id": journey1_id, "date": today, "client_id": clients[0]["id"], "provider_id": providers[0]["id"],
        "status": "in_progress", "packages_total": 25, "packages_delivered": 15, "packages_failed": 2, "packages_retry": 3,
        "start_data": {
            "departure_time": f"{today}T08:30:00", "odometer_start": 45230, "fuel_level": "Lleno",
            "vehicle_condition": "Bueno", "packages_loaded": 25, "started_at": datetime.now(timezone.utc).isoformat(),
        },
        "close_data": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.journeys.insert_one(journey1)

    journey2_id = str(uuid.uuid4())
    journey2 = {
        "id": journey2_id, "date": yesterday, "client_id": clients[1]["id"], "provider_id": providers[1]["id"],
        "status": "closed", "packages_total": 30, "packages_delivered": 27, "packages_failed": 2, "packages_retry": 1,
        "start_data": {
            "departure_time": f"{yesterday}T09:00:00", "odometer_start": 44800, "fuel_level": "3/4",
            "vehicle_condition": "Bueno", "packages_loaded": 30, "started_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
        "close_data": {
            "closed_at": f"{yesterday}T18:30:00", "odometer_end": 44950,
            "packages_delivered": 27, "packages_failed": 2, "packages_to_retry": 1,
            "km_traveled": 150, "delivery_rate": 90.0,
        },
        "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    await db.journeys.insert_one(journey2)

    for i in range(25):
        pkg = {
            "id": str(uuid.uuid4()), "journey_id": journey1_id,
            "tracking_number": f"TRK{1000+i}", "recipient_name": f"Cliente {i+1}",
            "address": f"Calle {i+1} #100, Col. Centro",
            "zone": "Zona Norte" if i < 12 else "Zona Sur",
            "delivery_window": "09:00-12:00" if i < 12 else "12:00-15:00",
            "status": "delivered" if i < 15 else ("failed" if i < 17 else "pending"),
            "is_retry": i >= 22,
        }
        await db.packages.insert_one(pkg)

    for i in range(30):
        pkg = {
            "id": str(uuid.uuid4()), "journey_id": journey2_id,
            "tracking_number": f"TRK{2000+i}", "recipient_name": f"Cliente {i+1}",
            "address": f"Av Principal {i*10}, Col. Industrial",
            "zone": "Zona Industrial", "delivery_window": "10:00-14:00",
            "status": "delivered" if i < 27 else ("failed" if i < 29 else "retry"),
            "is_retry": False,
        }
        await db.packages.insert_one(pkg)

    incidents = [
        {
            "id": str(uuid.uuid4()), "journey_id": journey1_id, "occurred_at": f"{today}T10:30:00",
            "incident_type": "Destinatario ausente", "description": "Cliente no se encontraba en domicilio",
            "severity": "Bajo", "tracking_number": "TRK1015", "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid.uuid4()), "journey_id": journey1_id, "occurred_at": f"{today}T12:15:00",
            "incident_type": "Tiempo excesivo por entrega", "description": "Tráfico intenso en zona centro",
            "severity": "Medio", "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid.uuid4()), "journey_id": journey2_id, "occurred_at": f"{yesterday}T14:00:00",
            "incident_type": "Llanta ponchada", "description": "Se reventó llanta trasera derecha",
            "severity": "Alto", "action_taken": "Se cambió por llanta de refacción",
            "status": "resolved", "resolved_at": f"{yesterday}T15:30:00",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    ]
    await db.incidents.insert_many(incidents)

    return {
        "message": "Base de datos inicializada exitosamente",
        "data": {"clients": len(clients), "providers": len(providers), "users": len(users), "journeys": 2, "packages": 55, "incidents": len(incidents)},
    }


# ==================== CLEANUP ====================

@router.post("/cleanup/routes-packages")
async def cleanup_routes_packages(user: dict = Depends(require_role(["coordinator", "developer"]))):
    j_del = await db.journeys.delete_many({})
    p_del = await db.packages.delete_many({})
    i_del = await db.incidents.delete_many({})
    return {
        "message": "Datos limpiados",
        "deleted": {"journeys": j_del.deleted_count, "packages": p_del.deleted_count, "incidents": i_del.deleted_count},
    }
