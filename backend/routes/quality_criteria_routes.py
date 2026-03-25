"""
Quality evaluation criteria management routes.
Allows Coordinator and Developer to configure evidence scoring rules and AI evaluation criteria.
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from dependencies import db, require_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Quality Criteria"])

DEFAULT_CRITERIA = {
    "version": 1,
    "third_party_keywords": [
        "vecino", "vigilante", "tercero", "familiar", "portero",
        "guardia", "recepción", "conserje", "seguridad", "caseta",
    ],
    "delivery_types": {
        "exitosa": {
            "label": "Entrega Exitosa",
            "required_evidence": [
                {"key": "foto_fachada", "label": "Foto de fachada del domicilio", "required": True, "weight": 30},
                {"key": "foto_paquete_guia", "label": "Foto del paquete con guía legible", "required": True, "weight": 35},
                {"key": "foto_receptor", "label": "Foto del receptor", "required": True, "weight": 35},
            ],
            "scoring_rules": {
                "3_photos": {"min_photos": 3, "score": 100, "label": "3+ fotos = 100%"},
                "2_photos": {"min_photos": 2, "score": 70, "label": "2 fotos = 70%"},
                "1_photo": {"min_photos": 1, "score": 40, "label": "1 foto = 40%"},
                "0_photos": {"min_photos": 0, "score": 0, "label": "Sin fotos = 0%"},
            },
        },
        "terceros": {
            "label": "Entrega a Terceros",
            "required_evidence": [
                {"key": "foto_fachada", "label": "Foto de fachada del domicilio", "required": True, "weight": 25},
                {"key": "foto_paquete_guia", "label": "Foto del paquete con guía legible", "required": True, "weight": 25},
                {"key": "foto_receptor", "label": "Foto de la persona (tercero)", "required": True, "weight": 25},
                {"key": "nota_driver", "label": "Nota confirmando a quién se entregó", "required": True, "weight": 25},
            ],
            "scoring_rules": {
                "complete": {"min_photos": 3, "requires_note": True, "score": 100, "label": "3+ fotos + nota = 100%"},
                "photos_no_note": {"min_photos": 3, "requires_note": False, "score": 70, "label": "3+ fotos sin nota = 70%"},
                "partial": {"min_photos": 1, "requires_note": False, "score": 50, "label": "Parcial = 50%"},
            },
        },
        "fallida": {
            "label": "Entrega Fallida",
            "required_evidence": [
                {"key": "foto_fachada", "label": "Foto de fachada antes de retirarse", "required": True, "weight": 100},
            ],
            "scoring_rules": {
                "has_photo": {"min_photos": 1, "score": 100, "label": "1+ foto = 100%"},
                "no_photo": {"min_photos": 0, "score": 0, "label": "Sin foto = 0%"},
            },
            "notes": "Kosmo no permite agregar notas del driver en entregas fallidas. No se evalúa la ausencia de nota como criterio faltante.",
        },
    },
    "ai_evaluation": {
        "enabled": True,
        "model": "claude-sonnet-4-5-20250929",
        "provider": "anthropic",
        "custom_instructions": "",
    },
}


@router.get("/quality/criteria")
async def get_quality_criteria(
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    criteria = await db.system_config.find_one({"key": "quality_criteria"}, {"_id": 0})
    if not criteria:
        return DEFAULT_CRITERIA
    return criteria.get("value", DEFAULT_CRITERIA)


@router.put("/quality/criteria")
async def update_quality_criteria(
    data: dict,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    current = await db.system_config.find_one({"key": "quality_criteria"}, {"_id": 0})
    current_value = current.get("value", DEFAULT_CRITERIA) if current else DEFAULT_CRITERIA.copy()

    if "third_party_keywords" in data:
        current_value["third_party_keywords"] = data["third_party_keywords"]

    if "delivery_types" in data:
        for dtype, dconfig in data["delivery_types"].items():
            if dtype in current_value["delivery_types"]:
                if "required_evidence" in dconfig:
                    current_value["delivery_types"][dtype]["required_evidence"] = dconfig["required_evidence"]
                if "scoring_rules" in dconfig:
                    current_value["delivery_types"][dtype]["scoring_rules"] = dconfig["scoring_rules"]
                if "notes" in dconfig:
                    current_value["delivery_types"][dtype]["notes"] = dconfig["notes"]

    if "ai_evaluation" in data:
        current_value["ai_evaluation"] = {
            **current_value.get("ai_evaluation", {}),
            **data["ai_evaluation"],
        }

    current_value["version"] = current_value.get("version", 0) + 1
    current_value["updated_at"] = datetime.now(timezone.utc).isoformat()
    current_value["updated_by"] = user.get("name", user["email"])

    await db.system_config.update_one(
        {"key": "quality_criteria"},
        {"$set": {"value": current_value, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )

    # Log change in audit
    await db.audit_log.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_role": user["role"],
        "action": "quality_criteria_updated",
        "resource_type": "system_config",
        "details": f"Criterios de calidad actualizados por {user.get('name', user['email'])}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"message": "Criterios actualizados exitosamente", "version": current_value["version"]}


@router.post("/quality/criteria/reset")
async def reset_quality_criteria(
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    default_with_meta = DEFAULT_CRITERIA.copy()
    default_with_meta["version"] = 1
    default_with_meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    default_with_meta["updated_by"] = user.get("name", user["email"])

    await db.system_config.update_one(
        {"key": "quality_criteria"},
        {"$set": {"value": default_with_meta, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )

    return {"message": "Criterios restablecidos a valores predeterminados", "criteria": default_with_meta}
