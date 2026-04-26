"""
Quality Tab routes - Quality summary, training samples, and package review
for the Journey Detail Quality tab redesign.
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from dependencies import db, get_current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Quality Tab"])


# ==================== QUALITY SUMMARY ====================

@router.get("/journeys/{journey_id}/quality-summary")
async def get_quality_summary(journey_id: str, user: dict = Depends(get_current_user)):
    """Return quality KPIs, distribution, error summary for a journey."""
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0, "driver_name": 1})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    packages = await db.packages.find(
        {"journey_id": journey_id, "status": {"$in": ["delivered", "failed"]}},
        {"_id": 0}
    ).to_list(5000)

    # Get config targets
    kpi_doc = await db.config.find_one({"key": "kpi_targets"}, {"_id": 0})
    kpi_targets = kpi_doc.get("value", {}) if kpi_doc else {}
    score_target = kpi_targets.get("score_target", 90)

    # Get error catalog for label lookups
    err_doc = await db.config.find_one({"key": "error_catalog"}, {"_id": 0})
    error_catalog = err_doc.get("value", []) if err_doc else []
    catalog_map = {e["key"]: e for e in error_catalog}

    scored = [p for p in packages if p.get("evidence_score") is not None]
    scores = [p["evidence_score"] for p in scored]
    score_avg = round(sum(scores) / len(scores), 1) if scores else 0

    complete = sum(1 for s in scores if s == 100)
    incomplete = sum(1 for s in scores if s == 0)
    partial = len(scores) - complete - incomplete
    total = len(scores)

    complete_pct = round(complete / total * 100, 1) if total else 0
    partial_pct = round(partial / total * 100, 1) if total else 0
    incomplete_pct = round(incomplete / total * 100, 1) if total else 0

    # Count IA evaluated
    evaluated_ia = sum(1 for p in scored if p.get("evidence_method") == "ai")

    # Average confidence
    confidences = [p.get("ia_confidence", 0) for p in scored if p.get("ia_confidence") is not None]
    confidence_avg = round(sum(confidences) / len(confidences) * 100, 1) if confidences else 0

    # Reviewed count
    reviewed_count = sum(1 for p in packages if p.get("review_status") in ("approved", "rejected"))

    # Error summary - aggregate ia_errors across all packages
    error_counts = {}
    for p in scored:
        for err_key in (p.get("ia_errors") or []):
            error_counts[err_key] = error_counts.get(err_key, 0) + 1

    # Also parse legacy missing_items into error keys
    for p in scored:
        if not p.get("ia_errors") and p.get("evidence_detail", {}).get("missing_items"):
            seen = set()
            for item in p["evidence_detail"]["missing_items"]:
                key = _infer_error_key(item)
                if key and key not in seen:
                    error_counts[key] = error_counts.get(key, 0) + 1
                    seen.add(key)

    error_summary = sorted(
        [
            {
                "key": k,
                "label": catalog_map.get(k, {}).get("label", k.replace("_", " ").title()),
                "count": v,
                "severity": _get_error_severity(k, catalog_map),
            }
            for k, v in error_counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:5]

    driver_name = journey.get("driver_name", "el driver")
    top_error = error_summary[0]["label"] if error_summary else None
    action_suggestion = (
        f"Notificar a {driver_name} sobre el estándar de {top_error.lower()} antes de la próxima ruta."
        if top_error else None
    )

    return {
        "score_avg": score_avg,
        "score_target": score_target,
        "distribution": {
            "complete": complete,
            "partial": partial,
            "incomplete": incomplete,
            "complete_pct": complete_pct,
            "partial_pct": partial_pct,
            "incomplete_pct": incomplete_pct,
        },
        "evaluated_ia": evaluated_ia,
        "total": total,
        "confidence_avg": confidence_avg,
        "reviewed_count": reviewed_count,
        "error_summary": error_summary,
        "action_suggestion": action_suggestion,
    }


# ==================== PACKAGES QUALITY ====================

@router.get("/journeys/{journey_id}/packages-quality")
async def get_packages_quality(
    journey_id: str,
    alerts_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Return quality details for packages in a journey with new structured fields."""
    query = {"journey_id": journey_id, "status": {"$in": ["delivered", "failed"]}}
    if alerts_only:
        query["$or"] = [
            {"ia_errors": {"$exists": True, "$ne": []}},
            {"evidence_detail.missing_items": {"$exists": True, "$ne": []}},
        ]

    total_count = await db.packages.count_documents(query)
    skip = (page - 1) * page_size

    packages = await db.packages.find(
        query, {"_id": 0}
    ).sort("evidence_score", 1).skip(skip).limit(page_size).to_list(page_size)
    # PII at-rest: decrypt + role-based mask
    from utils.pii import apply_pii_visibility_pkgs
    apply_pii_visibility_pkgs(packages, user.get("role"))

    # Enrich packages with structured quality fields
    result = []
    for p in packages:
        guide = p.get("tracking_number") or p.get("order_reference_id") or ""
        photo_count = len(p.get("kosmo_proof_urls") or [])

        # Build ia_errors from legacy data if not present
        ia_errors = p.get("ia_errors") or []
        ia_severity = p.get("ia_severity") or {}
        if not ia_errors and p.get("evidence_detail", {}).get("missing_items"):
            seen = set()
            for item in p["evidence_detail"]["missing_items"]:
                key = _infer_error_key(item)
                if key and key not in seen:
                    ia_errors.append(key)
                    ia_severity[key] = "critical"
                    seen.add(key)

        result.append({
            "id": p.get("id"),
            "guide": guide,
            "delivery_type": p.get("evidence_type", ""),
            "status": p.get("status", ""),
            "ia_score": p.get("evidence_score"),
            "ia_confidence": p.get("ia_confidence"),
            "ia_errors": ia_errors,
            "ia_severity": ia_severity,
            "ia_feedback": p.get("ia_feedback") or p.get("evidence_detail", {}).get("ai_observations", ""),
            "ia_evaluated_at": p.get("evidence_evaluated_at"),
            "evidence_method": p.get("evidence_method"),
            "attempt_number": p.get("attempt_number", 1),
            "review_status": p.get("review_status", "pending"),
            "reviewed_by": p.get("reviewed_by"),
            "photo_count": photo_count,
            "kosmo_proof_urls": p.get("kosmo_proof_urls") or [],
            "kosmo_note": p.get("kosmo_driver_note"),
            "tracking_url": p.get("tracking_url"),
            "evidence_detail": p.get("evidence_detail") or {},
            "recipient_name": p.get("recipient_name", ""),
        })

    return {
        "packages": result,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "pages": (total_count + page_size - 1) // page_size,
    }


# ==================== TRAINING SAMPLES ====================

@router.post("/training/samples")
async def save_training_sample(
    payload: dict,
    user: dict = Depends(require_role(["coordinator", "developer", "agent"])),
):
    """Save a training sample for supervised learning."""
    journey_id = payload.get("journey_id")
    guide = payload.get("guide")
    human_label = payload.get("human_label")  # "correct" or "incorrect"
    human_note = payload.get("human_note", "")
    corrected_score = payload.get("corrected_score")
    corrected_errors = payload.get("corrected_errors", [])

    if not journey_id or not guide or human_label not in ("correct", "incorrect"):
        raise HTTPException(status_code=400, detail="Campos requeridos: journey_id, guide, human_label (correct/incorrect)")

    # Read current IA result from package
    pkg = await db.packages.find_one(
        {"journey_id": journey_id, "$or": [
            {"order_reference_id": guide},
            {"tracking_number": guide},
        ]},
        {"_id": 0}
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")

    sample_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    sample = {
        "id": sample_id,
        "journey_id": journey_id,
        "guide": guide,
        "delivery_type": pkg.get("evidence_type", ""),
        "ia_score": pkg.get("evidence_score", 0),
        "ia_errors": pkg.get("ia_errors", []),
        "ia_feedback": pkg.get("ia_feedback", ""),
        "ia_confidence": pkg.get("ia_confidence", 0),
        "human_label": human_label,
        "human_note": human_note,
        "corrected_score": corrected_score,
        "corrected_errors": corrected_errors,
        "labeled_by": user.get("name", user["email"]),
        "labeled_at": now,
    }

    await db.training_samples.insert_one(sample)

    # Update package review status and optionally override score
    review_status = "approved" if human_label == "correct" else "rejected"
    update_fields = {
        "review_status": review_status,
        "reviewed_by": user.get("name", user["email"]),
        "reviewed_at": now,
        "review_note": human_note,
    }

    # If corrected score provided and label is incorrect, override the score
    if human_label == "incorrect" and corrected_score is not None:
        update_fields["evidence_score"] = corrected_score
        update_fields["evidence_score_override"] = True
        update_fields["evidence_score_original"] = pkg.get("evidence_score")

    # If corrected errors provided, store them
    if human_label == "incorrect" and corrected_errors:
        update_fields["ia_errors_corrected"] = corrected_errors

    await db.packages.update_one(
        {"id": pkg["id"]},
        {"$set": update_fields}
    )

    total = await db.training_samples.count_documents({})

    return {"id": sample_id, "total_samples": total, "review_status": review_status}


# ==================== PACKAGE REVIEW ====================

@router.patch("/journeys/{journey_id}/packages/{guide}/review")
async def update_package_review(
    journey_id: str,
    guide: str,
    payload: dict,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Update a package's review status."""
    review_status = payload.get("review_status")
    if review_status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="review_status debe ser 'approved' o 'rejected'")

    now = datetime.now(timezone.utc).isoformat()
    result = await db.packages.update_one(
        {"journey_id": journey_id, "$or": [
            {"order_reference_id": guide},
            {"tracking_number": guide},
        ]},
        {"$set": {
            "review_status": review_status,
            "reviewed_by": user.get("name", user["email"]),
            "reviewed_at": now,
            "review_note": payload.get("review_note"),
        }}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")

    return {"success": True, "review_status": review_status}


# ==================== HELPERS ====================

def _infer_error_key(missing_text: str) -> Optional[str]:
    """Map legacy missing_items text to error catalog keys."""
    text = missing_text.lower()
    if "fachada" in text:
        return "falta_fachada"
    if "guía" in text or "guia" in text or "legible" in text:
        return "guia_no_visible"
    if "receptor" in text or "titular" in text or "persona" in text:
        return "sin_foto_receptor"
    if "borrosa" in text or "enfoque" in text or "borroso" in text:
        return "foto_borrosa"
    if "paquete" in text and ("fuera" in text or "cortado" in text or "encuadre" in text):
        return "paquete_fuera_frame"
    if "whatsapp" in text or "sms" in text or "llamada" in text:
        return "falta_whatsapp"
    if "nota" in text and ("driver" in text or "confirmación" in text):
        return "sin_foto_receptor"
    return None


def _get_error_severity(key: str, catalog_map: dict) -> str:
    """Get severity for an error key from catalog."""
    entry = catalog_map.get(key, {})
    sev = entry.get("severity")
    if sev:
        return sev
    # Default severity based on error key
    critical_keys = {"sin_foto_receptor", "guia_no_visible", "falta_fachada", "foto_borrosa"}
    return "critical" if key in critical_keys else "warning"
