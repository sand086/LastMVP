"""
Platform Manuals routes — Knowledge Hub for operations teams.
CRUD for manuals + public reader endpoints.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import db, get_current_user, require_role
from pagination_utils import paginated_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Manuals"])

VALID_SECTIONS = ["Paneles", "Operación de Envíos", "Configuración", "Integraciones", "Inteligencia Artificial", "Documentación Técnica"]
VALID_PLATFORMS = ["web", "app", "both"]


class ManualCreate(BaseModel):
    title: str
    subtitle: Optional[str] = ""
    section: str
    tags: list[str] = []
    icon_key: Optional[str] = "book-open"
    platform_type: Optional[str] = "both"
    sort_order: Optional[int] = 0
    is_published: Optional[bool] = True


class ManualUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    section: Optional[str] = None
    tags: Optional[list[str]] = None
    icon_key: Optional[str] = None
    platform_type: Optional[str] = None
    sort_order: Optional[int] = None
    is_published: Optional[bool] = None


class ManualPageUpdate(BaseModel):
    content: list[dict]


# ── PUBLIC: List manuals ────────────────────────────────────────
@router.get("/manuals")
async def list_manuals(
    section: Optional[str] = None,
    platform: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query = {"is_published": True}
    if section and section != "all":
        query["section"] = section
    if platform and platform != "all":
        query["platform_type"] = {"$in": [platform, "both"]}
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"subtitle": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    manuals = await db.manuals.find(query, {"_id": 0}).sort("sort_order", 1).to_list(200)
    # Standardized envelope (page=1, page_size=200 = no pagination in practice)
    return paginated_response(manuals, total=len(manuals), page=1, page_size=max(len(manuals), 1))


# ── PUBLIC: Get manual by slug ──────────────────────────────────
@router.get("/manuals/{slug}")
async def get_manual(slug: str, user: dict = Depends(get_current_user)):
    manual = await db.manuals.find_one({"slug": slug, "is_published": True}, {"_id": 0})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")

    page = await db.manual_pages.find_one({"manual_id": manual["id"]}, {"_id": 0})
    manual["content"] = page["content"] if page else []
    return manual


# ── ADMIN: List all (including drafts) ──────────────────────────
@router.get("/manuals-admin")
async def list_manuals_admin(user: dict = Depends(require_role(["coordinator", "developer"]))):
    manuals = await db.manuals.find({}, {"_id": 0}).sort("sort_order", 1).to_list(200)
    return paginated_response(manuals, total=len(manuals), page=1, page_size=max(len(manuals), 1))


# ── ADMIN: Create manual ────────────────────────────────────────
@router.post("/manuals-admin")
async def create_manual(data: ManualCreate, user: dict = Depends(require_role(["coordinator", "developer"]))):
    if data.section not in VALID_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Seccion invalida. Opciones: {VALID_SECTIONS}")

    slug = data.title.lower().strip().replace(" ", "-").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:60]

    existing = await db.manuals.find_one({"slug": slug}, {"_id": 0, "id": 1})
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    now = datetime.now(timezone.utc).isoformat()
    manual_id = str(uuid.uuid4())
    doc = {
        "id": manual_id,
        "slug": slug,
        "title": data.title.strip(),
        "subtitle": data.subtitle or "",
        "section": data.section,
        "tags": data.tags,
        "icon_key": data.icon_key or "book-open",
        "platform_type": data.platform_type or "both",
        "sort_order": data.sort_order or 0,
        "is_published": data.is_published if data.is_published is not None else True,
        "created_at": now,
        "created_by": user["id"],
    }
    await db.manuals.insert_one(doc)

    page_doc = {
        "id": str(uuid.uuid4()),
        "manual_id": manual_id,
        "content": [],
        "version": 1,
        "updated_at": now,
    }
    await db.manual_pages.insert_one(page_doc)

    return {"id": manual_id, "slug": slug, "message": "Manual creado"}


# ── ADMIN: Update manual metadata ──────────────────────────────
@router.patch("/manuals-admin/{manual_id}")
async def update_manual(manual_id: str, data: ManualUpdate, user: dict = Depends(require_role(["coordinator", "developer"]))):
    manual = await db.manuals.find_one({"id": manual_id}, {"_id": 0, "id": 1})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.title is not None:
        update["title"] = data.title.strip()
    if data.subtitle is not None:
        update["subtitle"] = data.subtitle
    if data.section is not None:
        if data.section not in VALID_SECTIONS:
            raise HTTPException(status_code=400, detail="Seccion invalida")
        update["section"] = data.section
    if data.tags is not None:
        update["tags"] = data.tags
    if data.icon_key is not None:
        update["icon_key"] = data.icon_key
    if data.platform_type is not None:
        update["platform_type"] = data.platform_type
    if data.sort_order is not None:
        update["sort_order"] = data.sort_order
    if data.is_published is not None:
        update["is_published"] = data.is_published

    await db.manuals.update_one({"id": manual_id}, {"$set": update})
    return {"message": "Manual actualizado"}


# ── ADMIN: Update manual content (blocks) ──────────────────────
@router.put("/manuals-admin/{manual_id}/content")
async def update_manual_content(manual_id: str, data: ManualPageUpdate, user: dict = Depends(require_role(["coordinator", "developer"]))):
    manual = await db.manuals.find_one({"id": manual_id}, {"_id": 0, "id": 1})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")

    now = datetime.now(timezone.utc).isoformat()
    result = await db.manual_pages.update_one(
        {"manual_id": manual_id},
        {"$set": {"content": data.content, "updated_at": now}, "$inc": {"version": 1}},
    )
    if result.matched_count == 0:
        await db.manual_pages.insert_one({
            "id": str(uuid.uuid4()),
            "manual_id": manual_id,
            "content": data.content,
            "version": 1,
            "updated_at": now,
        })
    return {"message": "Contenido actualizado"}


# ── ADMIN: Delete manual ────────────────────────────────────────
@router.delete("/manuals-admin/{manual_id}")
async def delete_manual(manual_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.manuals.delete_one({"id": manual_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    await db.manual_pages.delete_many({"manual_id": manual_id})
    return {"message": "Manual eliminado"}


# ── ADMIN: Get manual with content for editing ─────────────────
@router.get("/manuals-admin/{manual_id}")
async def get_manual_admin(manual_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    manual = await db.manuals.find_one({"id": manual_id}, {"_id": 0})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    page = await db.manual_pages.find_one({"manual_id": manual_id}, {"_id": 0})
    manual["content"] = page["content"] if page else []
    return manual


@router.post("/manuals-admin/seed")
async def seed_manuals(
    force: bool = False,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Upsert manuals by slug from the canonical catalog at data/manual_seed.py.

    - When ?force=true: also overwrites content of existing manuals (re-publishes).
    - Default: inserts only missing slugs; existing manuals untouched.
    """
    from data.manual_seed import get_manuals_seed
    catalog = get_manuals_seed()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0

    for m in catalog:
        slug = m["slug"]
        existing = await db.manuals.find_one({"slug": slug}, {"_id": 0, "id": 1})
        content = list(m["content"])
        meta = {k: v for k, v in m.items() if k != "content"}
        meta["platform_type"] = meta.get("platform_type", "both")
        meta["is_published"] = meta.get("is_published", True)
        meta["updated_at"] = now

        if existing:
            if not force:
                continue
            manual_id = existing["id"]
            await db.manuals.update_one(
                {"id": manual_id},
                {"$set": {**meta, "updated_by": user["id"]}},
            )
            await db.manual_pages.update_one(
                {"manual_id": manual_id},
                {"$set": {"content": content, "version": (existing.get("version") or 1) + 1, "updated_at": now}},
                upsert=True,
            )
            updated += 1
        else:
            manual_id = str(uuid.uuid4())
            await db.manuals.insert_one({
                **meta,
                "id": manual_id,
                "slug": slug,
                "created_at": now,
                "created_by": user["id"],
            })
            await db.manual_pages.insert_one({
                "id": str(uuid.uuid4()),
                "manual_id": manual_id,
                "content": content,
                "version": 1,
                "updated_at": now,
            })
            inserted += 1

    return {
        "message": f"Seed completado: {inserted} insertados, {updated} actualizados (total catálogo: {len(catalog)})",
        "inserted": inserted,
        "updated": updated,
        "total_catalog": len(catalog),
        "force": force,
    }
