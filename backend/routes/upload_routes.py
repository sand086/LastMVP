"""
File upload routes: CSV/XLSX uploads, photo uploads, journey images.
"""
import uuid
import io
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from typing import List, Optional
from datetime import datetime, timezone

import pandas as pd

from dependencies import (
    db, limiter, get_current_user, require_role,
    UPLOAD_DIR, MAX_FILE_SIZE, _validate_upload_file,
)
from models import MessengerProviderMapping
from starlette.requests import Request as StarletteRequest
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Uploads"])


# ==================== HISTORY ORDERS UPLOAD (Step 1) ====================

@router.post("/upload/history-orders")
@limiter.limit("10/minute")
async def upload_history_orders(
    request: StarletteRequest,
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    _validate_upload_file(file)
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande. Máximo 10 MB.")

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))

        required_columns = ["order_id", "order_reference_id", "tracking_url"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(status_code=400, detail=f"Columnas faltantes: {', '.join(missing_columns)}")

        orders = df.to_dict('records')
        cleaned_orders = []
        for order in orders:
            cleaned_order = {}
            for key in order:
                if pd.isna(order[key]):
                    cleaned_order[key] = ""
                else:
                    cleaned_order[key] = str(order[key])
            cleaned_orders.append(cleaned_order)

        ignored_count = 0
        valid_orders = []
        for order in cleaned_orders:
            tracking = order.get("order_reference_id", "").strip()
            if not tracking:
                ignored_count += 1
                continue
            provider_val = order.get("provider", "").strip()
            if provider_val.upper() == "OWN_FLEET" and not tracking:
                ignored_count += 1
                continue
            first_key = list(order.keys())[0] if order else ""
            first_val = order.get(first_key, "").strip().lower()
            if first_val == first_key.lower():
                ignored_count += 1
                continue
            valid_orders.append(order)
        cleaned_orders = valid_orders

        routes = {}
        for order in cleaned_orders:
            route_id = order.get("order_id", "")
            if route_id:
                if route_id not in routes:
                    routes[route_id] = {
                        "route_id": route_id,
                        "driver_name": order.get("driver_name", ""),
                        "orders": [],
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
                    "created_at": order.get("created_at", ""),
                })

        return {
            "filename": file.filename,
            "total_orders": len(cleaned_orders),
            "total_routes": len(routes),
            "ignored_rows": ignored_count,
            "routes": list(routes.values()),
            "preview": cleaned_orders[:10],
        }
    except Exception as e:
        logger.error(f"Error parsing history-orders file: {e}")
        raise HTTPException(status_code=400, detail=f"Error al procesar archivo: {str(e)}")


# ==================== ROUTE SUMMARY UPLOAD (Step 2) ====================

@router.post("/upload/route-summary")
@limiter.limit("10/minute")
async def upload_route_summary(
    request: StarletteRequest,
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    _validate_upload_file(file)
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande. Máximo 10 MB.")

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))

        required_columns = ["Order ID", "Driver"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(status_code=400, detail=f"Columnas faltantes: {', '.join(missing_columns)}")

        routes = df.to_dict('records')
        cleaned_routes = []
        for route in routes:
            cleaned_route = {}
            for key in route:
                if pd.isna(route[key]):
                    cleaned_route[key] = ""
                else:
                    cleaned_route[key] = str(route[key])
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
                    "pending_stops": cleaned_route.get("Pending Stops", "0"),
                })

        drivers = list(set(r["driver_name"] for r in cleaned_routes if r["driver_name"]))

        # Detect new drivers and new providers (Teams)
        teams_in_csv = {}
        for r in cleaned_routes:
            dn = r.get("driver_name", "").strip()
            team = r.get("team", "").strip()
            if dn and team:
                teams_in_csv[dn] = team

        # Get existing providers by name
        existing_providers = await db.providers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
        provider_names_lower = {p["name"].lower(): p for p in existing_providers}

        # Get existing messenger mappings
        existing_mappings = await db.messenger_mappings.find({}, {"_id": 0}).to_list(500)
        mapping_by_driver = {m["messenger_name"]: m.get("provider_id", "") for m in existing_mappings}

        # Identify pending providers that don't exist
        pending_providers = []
        seen_teams = set()
        driver_status = []
        for driver_name in sorted(drivers):
            team = teams_in_csv.get(driver_name, "")
            has_mapping = driver_name in mapping_by_driver and mapping_by_driver[driver_name]
            team_exists = team.lower() in provider_names_lower if team else True

            if not has_mapping and team and not team_exists and team not in seen_teams:
                pending_providers.append({
                    "team_name": team,
                    "drivers": [dn for dn, t in teams_in_csv.items() if t == team],
                })
                seen_teams.add(team)

            driver_status.append({
                "name": driver_name,
                "team": team,
                "has_mapping": has_mapping,
                "team_exists": team_exists,
                "needs_new_provider": not has_mapping and team and not team_exists,
            })

        return {
            "filename": file.filename,
            "total_routes": len(cleaned_routes),
            "routes": cleaned_routes,
            "drivers": sorted(drivers),
            "driver_status": driver_status,
            "pending_providers": pending_providers,
            "preview": cleaned_routes[:10],
        }
    except Exception as e:
        logger.error(f"Error parsing route-summary file: {e}")
        raise HTTPException(status_code=400, detail=f"Error al procesar archivo: {str(e)}")


# ==================== LEGACY LAYOUT UPLOAD ====================

@router.post("/upload/layout")
async def upload_layout(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    if not file.filename.endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos CSV o XLSX")
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede 5MB")
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        required_columns = ["tracking_number", "recipient_name", "address", "zone", "delivery_window"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(status_code=400, detail=f"Columnas faltantes: {', '.join(missing_columns)}")
        packages = df.to_dict('records')
        for pkg in packages:
            for key in pkg:
                if pd.isna(pkg[key]):
                    pkg[key] = ""
                else:
                    pkg[key] = str(pkg[key])
        return {"filename": file.filename, "total_rows": len(packages), "preview": packages[:10], "packages": packages}
    except Exception as e:
        logger.error(f"Error parsing file: {e}")
        raise HTTPException(status_code=400, detail=f"Error al procesar archivo: {str(e)}")


# ==================== PHOTO / IMAGE UPLOADS ====================

@router.post("/upload/photo")
async def upload_photo(
    file: UploadFile = File(...),
    journey_id: str = Form(...),
    photo_type: str = Form(...),
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos JPG o PNG")
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede 5MB")
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    filename = f"{journey_id}_{photo_type}_{file_id}{ext}"
    filepath = UPLOAD_DIR / filename
    with open(filepath, "wb") as f:
        f.write(contents)
    return {"filename": filename, "path": f"/api/uploads/{filename}"}


@router.post("/upload/journey-images")
async def upload_journey_images(
    files: List[UploadFile] = File(...),
    journey_id: str = Form(...),
    section: str = Form(...),
    incident_id: Optional[str] = Form(None),
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    uploaded_files = []
    for file in files:
        if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            continue
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
            "uploaded_by": user["id"],
        }
        await db.journey_images.insert_one(image_record)
        uploaded_files.append({k: v for k, v in image_record.items() if k != "_id"})
    return {"uploaded": len(uploaded_files), "files": uploaded_files}


@router.get("/journey-images/{journey_id}")
async def get_journey_images(
    journey_id: str,
    section: Optional[str] = None,
    incident_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query = {"journey_id": journey_id}
    if section:
        query["section"] = section
    if incident_id:
        query["incident_id"] = incident_id
    images = await db.journey_images.find(query, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
    return images


@router.delete("/journey-images/{image_id}")
async def delete_journey_image(
    image_id: str,
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    image = await db.journey_images.find_one({"id": image_id}, {"_id": 0})
    if not image:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    filepath = UPLOAD_DIR / image["filename"]
    if filepath.exists():
        filepath.unlink()
    await db.journey_images.delete_one({"id": image_id})
    return {"message": "Imagen eliminada"}


@router.get("/uploads/{filename}")
async def get_upload(filename: str):
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(filepath)


@router.get("/template/layout")
async def download_template():
    template_data = "tracking_number,recipient_name,address,zone,delivery_window\nTRK001,Juan Pérez,Calle 123 Col Centro,Zona Norte,09:00-12:00\nTRK002,María García,Av Principal 456,Zona Sur,12:00-15:00"
    return Response(
        content=template_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantilla_layout.csv"},
    )


# ==================== MESSENGER-PROVIDER MAPPING ====================

@router.get("/messenger-mappings")
async def get_messenger_mappings(user: dict = Depends(get_current_user)):
    mappings = await db.messenger_mappings.find({}, {"_id": 0}).to_list(500)
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    for m in mappings:
        m["provider_name"] = providers.get(m.get("provider_id"), "Sin asignar")
    return mappings


@router.post("/messenger-mappings")
async def save_messenger_mappings(
    mappings: List[MessengerProviderMapping],
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    for mapping in mappings:
        await db.messenger_mappings.update_one(
            {"messenger_name": mapping.messenger_name},
            {"$set": {
                "messenger_name": mapping.messenger_name,
                "provider_id": mapping.provider_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": user["id"],
            }},
            upsert=True,
        )
    return {"message": f"{len(mappings)} asignaciones guardadas"}


@router.delete("/messenger-mappings/{messenger_name}")
async def delete_messenger_mapping(
    messenger_name: str,
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    result = await db.messenger_mappings.delete_one({"messenger_name": messenger_name})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Mapping no encontrado")
    return {"message": "Asignación eliminada"}


# ═══════════════════════════════════════════════════
# Update delivery notes from history-orders CSV
# ═══════════════════════════════════════════════════
@router.post("/upload/update-notes")
async def update_delivery_notes(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """
    Upsert failure_reason_note and note_from_driver from a history-orders CSV/XLSX.
    Matches on order_reference_id (tracking_number). Idempotent.
    """
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Solo archivos CSV o XLSX")

    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al leer archivo: {e}")

    # Require at least order_reference_id column
    id_col = None
    for candidate in ["order_reference_id", "tracking_number", "order_id"]:
        if candidate in df.columns:
            id_col = candidate
            break
    if not id_col:
        raise HTTPException(status_code=400, detail="Columna de identificador no encontrada. Se requiere: order_reference_id, tracking_number u order_id")

    # Check which note columns exist
    has_failure_note = "failure_reason_note" in df.columns
    has_driver_note = "note_from_driver" in df.columns
    has_failure_reason = "failure_reason" in df.columns
    if not has_failure_note and not has_driver_note:
        raise HTTPException(status_code=400, detail="El archivo no contiene columnas failure_reason_note ni note_from_driver")

    total = 0
    updated = 0
    not_found = 0
    errors = 0

    for _, row in df.iterrows():
        total += 1
        tracking = str(row.get(id_col, "")).strip()
        if not tracking or tracking == "nan":
            errors += 1
            continue

        # Build update fields — only non-empty values
        update_fields = {}
        if has_failure_note:
            val = str(row.get("failure_reason_note", "")).strip()
            if val and val != "nan":
                update_fields["failure_reason_note"] = val
        if has_driver_note:
            val = str(row.get("note_from_driver", "")).strip()
            if val and val != "nan":
                update_fields["note_from_driver"] = val
        if has_failure_reason:
            val = str(row.get("failure_reason", "")).strip()
            if val and val != "nan":
                update_fields["failure_reason"] = val

        if not update_fields:
            continue

        # Match by order_reference_id or tracking_number
        result = await db.packages.update_many(
            {"$or": [
                {"order_reference_id": tracking},
                {"tracking_number": tracking},
            ]},
            {"$set": update_fields},
        )
        if result.matched_count > 0:
            updated += result.modified_count or result.matched_count
        else:
            not_found += 1

    return {
        "message": f"Notas actualizadas: {updated} registros",
        "total_rows": total,
        "updated": updated,
        "not_found": not_found,
        "errors": errors,
        "columns_processed": [c for c in ["failure_reason_note", "note_from_driver", "failure_reason"] if c in df.columns],
    }
