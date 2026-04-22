"""Architecture snapshot API — live documentation auto-generated from the codebase."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import db, get_current_user, require_role
from architecture_scanner import generate_snapshot, diff_snapshots
from pagination_utils import paginated_response

router = APIRouter(prefix="/architecture", tags=["architecture"])

CURRENT_VERSION = "current"  # Alias to fetch latest without id


# ── GET /api/architecture/snapshot ─────────────────────────────────
@router.get("/snapshot")
async def get_current_snapshot(user: dict = Depends(get_current_user)):
    """Retorna el ultimo snapshot almacenado. Si no existe, genera uno nuevo."""
    latest = await db.architecture_snapshots.find_one(
        {}, {"_id": 0}, sort=[("generated_at", -1)]
    )
    if not latest:
        # Primera llamada: generar y persistir automaticamente
        snapshot = generate_snapshot()
        snapshot["id"] = str(uuid.uuid4())
        snapshot["triggered_by"] = "auto_first_run"
        snapshot["triggered_by_user"] = user.get("id")
        await db.architecture_snapshots.insert_one(dict(snapshot))
        return snapshot
    return latest


# ── POST /api/architecture/regenerate ──────────────────────────────
@router.post("/regenerate")
async def regenerate_snapshot(user: dict = Depends(require_role(["developer", "executive"]))):
    """Genera un nuevo snapshot y detecta cambios vs el anterior."""
    prev = await db.architecture_snapshots.find_one(
        {}, {"_id": 0}, sort=[("generated_at", -1)]
    )
    snapshot = generate_snapshot()

    # Short-circuit si no hay cambios reales (ahorra espacio)
    if prev and prev.get("content_hash") == snapshot["content_hash"]:
        return {
            "status": "unchanged",
            "message": "No se detectaron cambios estructurales; snapshot existente conservado.",
            "snapshot_id": prev.get("id"),
            "content_hash": snapshot["content_hash"],
        }

    snapshot["id"] = str(uuid.uuid4())
    snapshot["triggered_by"] = "manual"
    snapshot["triggered_by_user"] = user.get("id")

    # Calcular diff y almacenar en changelog
    diff_result = None
    if prev:
        diff_result = diff_snapshots(prev, snapshot)
        snapshot["diff_from_previous"] = diff_result
        if diff_result["is_significant"]:
            await db.architecture_changelog.insert_one({
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_snapshot_id": prev.get("id"),
                "to_snapshot_id": snapshot["id"],
                "changes": diff_result["changes"],
                "total_changes": diff_result["total_changes"],
                "triggered_by_user": user.get("id"),
            })

    await db.architecture_snapshots.insert_one(dict(snapshot))

    # Housekeeping: mantener solo los ultimos 20 snapshots
    count = await db.architecture_snapshots.count_documents({})
    if count > 20:
        oldest = await db.architecture_snapshots.find(
            {}, {"_id": 1}, sort=[("generated_at", 1)], limit=count - 20
        ).to_list(count - 20)
        await db.architecture_snapshots.delete_many({"_id": {"$in": [o["_id"] for o in oldest]}})

    return {
        "status": "regenerated",
        "snapshot_id": snapshot["id"],
        "content_hash": snapshot["content_hash"],
        "diff": diff_result,
    }


# ── GET /api/architecture/history ──────────────────────────────────
@router.get("/history")
async def history(user: dict = Depends(get_current_user), limit: int = 20):
    snapshots = await db.architecture_snapshots.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "generated_at": 1,
            "content_hash": 1,
            "triggered_by": 1,
            "stats": 1,
        },
    ).sort("generated_at", -1).to_list(limit)
    return paginated_response(snapshots, total=len(snapshots), page=1, page_size=limit)


# ── GET /api/architecture/snapshot/{id} ────────────────────────────
@router.get("/snapshot/{snapshot_id}")
async def get_snapshot_by_id(snapshot_id: str, user: dict = Depends(get_current_user)):
    snap = await db.architecture_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot no encontrado")
    return snap


# ── GET /api/architecture/diff ─────────────────────────────────────
@router.get("/diff")
async def diff_two_snapshots(
    from_id: str = Query(...),
    to_id: str = Query(...),
    user: dict = Depends(get_current_user),
):
    prev = await db.architecture_snapshots.find_one({"id": from_id}, {"_id": 0})
    curr = await db.architecture_snapshots.find_one({"id": to_id}, {"_id": 0})
    if not prev or not curr:
        raise HTTPException(status_code=404, detail="Uno o ambos snapshots no existen")
    return {
        "from": {"id": from_id, "generated_at": prev["generated_at"]},
        "to": {"id": to_id, "generated_at": curr["generated_at"]},
        **diff_snapshots(prev, curr),
    }


# ── GET /api/architecture/changelog ────────────────────────────────
@router.get("/changelog")
async def changelog(user: dict = Depends(get_current_user), limit: int = 50):
    entries = await db.architecture_changelog.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)
    return paginated_response(entries, total=len(entries), page=1, page_size=limit)
