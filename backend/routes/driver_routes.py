"""
Driver Management routes — CRUD + population from historical data.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dependencies import db, get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Drivers"])


# ── Models ──────────────────────────────────────────────────────
class DriverUpdate(BaseModel):
    provider_id: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_custom: Optional[str] = None
    status: Optional[str] = None


class InlineProviderCreate(BaseModel):
    name: str
    contact_name: Optional[str] = ""
    contact_phone: Optional[str] = ""
    rfc: Optional[str] = ""
    status: Optional[str] = "active"
    created_via: Optional[str] = "layout_upload"


# ── GET /api/drivers/vehicle-types ──────────────────────────────
# NOTE: This route MUST be defined BEFORE /drivers/{driver_id} to avoid path conflict
@router.get("/drivers/vehicle-types")
async def get_vehicle_types(user: dict = Depends(get_current_user)):
    """Get distinct vehicle types from drivers collection."""
    types = await db.drivers.distinct("vehicle_type")
    types = [t for t in types if t]
    base_types = ["moto", "van", "camioneta", "auto"]
    all_types = list(dict.fromkeys(base_types + types))
    return all_types


# ── GET /api/drivers ────────────────────────────────────────────
@router.get("/drivers")
async def list_drivers(
    search: Optional[str] = None,
    provider_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    query = {}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    if provider_id:
        query["provider_id"] = provider_id
    if status and status != "all":
        query["status"] = status

    total = await db.drivers.count_documents(query)
    skip = (page - 1) * limit

    drivers = await db.drivers.find(
        query, {"_id": 0}
    ).sort("name", 1).skip(skip).limit(limit).to_list(limit)

    # Enrich with provider names
    provider_ids = list(set(d.get("provider_id") for d in drivers if d.get("provider_id")))
    providers_map = {}
    if provider_ids:
        provs = await db.providers.find(
            {"id": {"$in": provider_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(provider_ids))
        providers_map = {p["id"]: p["name"] for p in provs}

    for d in drivers:
        d["provider_name"] = providers_map.get(d.get("provider_id"), "")

    return {
        "data": drivers,
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
    }


# ── GET /api/drivers/:id ───────────────────────────────────────
@router.get("/drivers/{driver_id}")
async def get_driver(driver_id: str, user: dict = Depends(get_current_user)):
    driver = await db.drivers.find_one({"id": driver_id}, {"_id": 0})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver no encontrado")

    if driver.get("provider_id"):
        prov = await db.providers.find_one({"id": driver["provider_id"]}, {"_id": 0, "name": 1})
        driver["provider_name"] = prov["name"] if prov else ""

    return driver


# ── PATCH /api/drivers/:id ──────────────────────────────────────
@router.patch("/drivers/{driver_id}")
async def update_driver(
    driver_id: str,
    data: DriverUpdate,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    driver = await db.drivers.find_one({"id": driver_id}, {"_id": 0})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver no encontrado")

    update = {"updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}

    if data.provider_id is not None:
        if not data.provider_id:
            raise HTTPException(status_code=400, detail="El proveedor no puede estar vacio")
        prov = await db.providers.find_one({"id": data.provider_id}, {"_id": 0, "id": 1})
        if not prov:
            raise HTTPException(status_code=400, detail="Proveedor no encontrado")
        update["provider_id"] = data.provider_id
        # Also update messenger_mappings for future loads
        await db.messenger_mappings.update_one(
            {"messenger_name": driver["name"]},
            {"$set": {"provider_id": data.provider_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )

    if data.vehicle_type is not None:
        update["vehicle_type"] = data.vehicle_type
    if data.vehicle_custom is not None:
        update["vehicle_custom"] = data.vehicle_custom
    if data.status is not None:
        if data.status not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="Estado invalido")
        update["status"] = data.status

    await db.drivers.update_one({"id": driver_id}, {"$set": update})
    return {"message": "Driver actualizado", "id": driver_id}


# ── POST /api/drivers/populate ──────────────────────────────────
@router.post("/drivers/populate")
async def populate_drivers(
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Populate drivers collection from historical journey data."""
    now = datetime.now(timezone.utc).isoformat()

    # Get all unique driver names from journeys
    pipeline = [
        {"$match": {"driver_name": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": "$driver_name",
            "provider_id": {"$first": "$provider_id"},
            "first_date": {"$min": "$created_at"},
            "last_date": {"$max": "$created_at"},
            "total_routes": {"$sum": 1},
        }},
    ]
    results = []
    async for doc in db.journeys.aggregate(pipeline):
        results.append(doc)

    created = 0
    updated = 0
    for doc in results:
        name = doc["_id"]
        existing = await db.drivers.find_one({"name": name}, {"_id": 0, "id": 1})
        if existing:
            # Update stats only
            await db.drivers.update_one(
                {"id": existing["id"]},
                {"$set": {
                    "last_upload_at": doc.get("last_date", now),
                    "total_routes": doc["total_routes"],
                }},
            )
            updated += 1
        else:
            driver_doc = {
                "id": str(uuid.uuid4()),
                "name": name,
                "provider_id": doc.get("provider_id", ""),
                "vehicle_type": "",
                "vehicle_custom": None,
                "status": "active",
                "first_upload_at": doc.get("first_date", now),
                "last_upload_at": doc.get("last_date", now),
                "total_routes": doc["total_routes"],
                "created_via": "populate",
                "updated_at": now,
                "updated_by": user["id"],
            }
            await db.drivers.insert_one(driver_doc)
            created += 1

    return {"message": f"{created} drivers creados, {updated} actualizados", "created": created, "updated": updated}


# ── POST /api/providers/inline ──────────────────────────────────
@router.post("/providers/inline")
async def create_provider_inline(
    data: InlineProviderCreate,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Create a provider inline (from layout upload or settings modal)."""
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="El nombre del proveedor es requerido")

    # Check if provider already exists by name
    existing = await db.providers.find_one(
        {"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}},
        {"_id": 0, "id": 1, "name": 1},
    )
    if existing:
        return {"id": existing["id"], "name": existing["name"], "already_existed": True}

    now = datetime.now(timezone.utc).isoformat()
    provider_doc = {
        "id": str(uuid.uuid4()),
        "name": data.name.strip(),
        "contact_name": data.contact_name or "",
        "contact_phone": data.contact_phone or "",
        "rfc": data.rfc or "",
        "status": data.status or "active",
        "created_via": data.created_via or "manual",
        "created_at": now,
        "created_by": user["id"],
    }
    await db.providers.insert_one(provider_doc)
    return {"id": provider_doc["id"], "name": provider_doc["name"], "already_existed": False}
