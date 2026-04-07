"""
Quality evaluation criteria management routes.
Allows Coordinator and Developer to configure evidence scoring rules and AI evaluation criteria.
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta

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


# ==================== MASTER QUALITY SETTINGS ====================

DEFAULT_KPI_TARGETS = {
    "score_min_acceptable": 70,
    "score_target": 90,
    "score_excellent": 95,
    "weights": {"delivery_rate": 40, "visit_rate": 30, "evidence_quality": 30},
    "critical_failure_cap": {"trigger_key": "foto_paquete_guia", "max_score_if_failed": 40},
}

DEFAULT_SLA_BRACKETS = [
    {"id": "bracket_1", "label": "Mes 1-2", "description": "Arranque operativo", "target": 65, "status": "exceeded"},
    {"id": "bracket_2", "label": "Mes 3-4", "description": "Crecimiento", "target": 75, "status": "active"},
    {"id": "bracket_3", "label": "Mes 5+", "description": "Objetivo estable", "target": 90, "status": "pending"},
]

DEFAULT_SLA_TARGETS_BY_RUBRO = {
    "delivery_rate": {"target": 75, "label": "Tasa de entrega"},
    "visit_rate": {"target": 85, "label": "Tasa de visita efectiva"},
    "evidence_quality": {"target": 90, "label": "Calidad de evidencias"},
}

DEFAULT_PENALTY_RULES = [
    {"id": "p1", "label": "Sin evidencias (0 fotos)", "discount_pct": 100, "applies_to": "provider"},
    {"id": "p2", "label": "Evidencia parcial (1-2 fotos)", "discount_pct": 50, "applies_to": "provider"},
    {"id": "p3", "label": "Guía no legible en foto", "discount_pct": 60, "applies_to": "driver"},
    {"id": "p4", "label": "Sin nota en entrega a terceros", "discount_pct": 30, "applies_to": "driver"},
]

DEFAULT_STRIKE_POLICY = {
    "days_below_min_for_strike": 3,
    "strikes_for_formal_warning": 1,
    "strikes_for_cubbo_escalation": 3,
}

DEFAULT_IA_CONFIG = {
    "provider": "anthropic",
    "model": "claude-sonnet-4-5-20250929",
    "enabled": True,
    "auto_eval_on_close": False,
    "confidence_approve": 80,
    "confidence_review": 60,
    "system_prompt": "",
    "supervised_training_enabled": False,
}

DEFAULT_ERROR_CATALOG = [
    {"id": "falta_fachada", "key": "falta_fachada", "label": "Falta foto de fachada del domicilio", "applies_to": ["exitosa", "terceros", "fallida"], "active": True},
    {"id": "guia_no_visible", "key": "guia_no_visible", "label": "Guía de envío no visible o ilegible", "applies_to": ["exitosa", "terceros", "fallida"], "active": True},
    {"id": "foto_borrosa", "key": "foto_borrosa", "label": "Foto borrosa o sin foco", "applies_to": ["exitosa", "terceros", "fallida"], "active": True},
    {"id": "sin_foto_receptor", "key": "sin_foto_receptor", "label": "Falta foto del receptor o tercero", "applies_to": ["exitosa", "terceros"], "active": True},
    {"id": "paquete_fuera_frame", "key": "paquete_fuera_frame", "label": "Paquete fuera de encuadre o cortado", "applies_to": ["exitosa", "terceros", "fallida"], "active": True},
    {"id": "falta_whatsapp", "key": "falta_whatsapp", "label": "Falta captura de WhatsApp o SMS de notificación", "applies_to": ["fallida"], "active": True},
]

CONFIG_DEFAULTS = {
    "kpi_targets": DEFAULT_KPI_TARGETS,
    "sla_brackets": DEFAULT_SLA_BRACKETS,
    "sla_targets_by_rubro": DEFAULT_SLA_TARGETS_BY_RUBRO,
    "penalty_rules": DEFAULT_PENALTY_RULES,
    "strike_policy": DEFAULT_STRIKE_POLICY,
    "ia_config": DEFAULT_IA_CONFIG,
    "error_catalog": DEFAULT_ERROR_CATALOG,
}

QUALITY_CONFIG_KEYS = list(CONFIG_DEFAULTS.keys())


@router.get("/config/quality-settings")
async def get_quality_settings(
    user: dict = Depends(require_role(["coordinator", "developer", "executive"])),
):
    """Return all quality configuration documents in a single response."""
    result = {}
    for key in QUALITY_CONFIG_KEYS:
        doc = await db.config.find_one({"key": key}, {"_id": 0})
        if doc:
            result[key] = doc.get("value", CONFIG_DEFAULTS[key])
        else:
            result[key] = CONFIG_DEFAULTS[key]

    # Enrich error_catalog with frequency_last_30d
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    errors = result.get("error_catalog", [])
    for err in errors:
        count = await db.training_samples.count_documents({
            "error_type": err["key"],
            "labeled_at": {"$gte": thirty_days_ago},
        })
        err["frequency_last_30d"] = count

    result["error_catalog"] = errors

    # Get quality_criteria version for display
    qc = await db.system_config.find_one({"key": "quality_criteria"}, {"_id": 0})
    qc_val = qc.get("value", {}) if qc else {}
    result["_meta"] = {
        "version": qc_val.get("version", 1),
        "updated_by": qc_val.get("updated_by", ""),
        "updated_at": qc_val.get("updated_at", ""),
    }

    return result


@router.patch("/config/quality-settings")
async def patch_quality_settings(
    payload: dict,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Update a specific section of quality settings."""
    section = payload.get("section")
    value = payload.get("value")

    if not section or section not in QUALITY_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Section inválida: {section}. Opciones: {QUALITY_CONFIG_KEYS}")
    if value is None:
        raise HTTPException(status_code=400, detail="value requerido")

    # Read current doc
    doc = await db.config.find_one({"key": section}, {"_id": 0})
    current_version = doc.get("version", 0) if doc else 0

    await db.config.update_one(
        {"key": section},
        {"$set": {
            "value": value,
            "version": current_version + 1,
            "updated_by": user.get("name", user["email"]),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    # Also increment quality_criteria version in system_config for display
    await db.system_config.update_one(
        {"key": "quality_criteria"},
        {"$inc": {"value.version": 1}, "$set": {"value.updated_by": user.get("name", user["email"]), "value.updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )

    # Audit
    await db.audit_log.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_role": user["role"],
        "action": f"quality_config_{section}_updated",
        "resource_type": "config",
        "details": f"{section} actualizado por {user.get('name', user['email'])}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"success": True, "section": section, "version": current_version + 1}
