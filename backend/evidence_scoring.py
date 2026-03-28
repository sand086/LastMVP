"""
AI-Powered Evidence Quality Scoring Module
Uses OpenAI Vision (GPT-4o) via emergentintegrations for deep analysis of delivery evidence photos.
Falls back to rule-based scoring when AI is unavailable or images cannot be fetched.
Based on Cubbo delivery evidence standards.
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


def _get_db():
    """Get db reference for token logging."""
    from dependencies import db
    return db

THIRD_PARTY_KEYWORDS = [
    "vecino", "vigilante", "tercero", "familiar", "portero",
    "guardia", "recepción", "conserje", "seguridad", "caseta",
]

CUBBO_SYSTEM_PROMPT = """Eres un evaluador experto de evidencias fotográficas de entregas de última milla.
Evalúas fotos según el estándar Cubbo para entregas en México.

CRITERIOS POR TIPO DE ENTREGA:

**Entrega Exitosa:**
1. Foto de fachada del domicilio (debe verse número/dirección)
2. Foto del paquete con la guía legible (OCR del número de guía)
3. Foto del receptor/persona que recibe el paquete

**Entrega a Terceros:**
1. Foto de fachada del domicilio
2. Foto del paquete con la guía legible
3. Foto de la persona (tercero) que recibe
4. Nota del driver confirmando a quién se entregó

**Entrega Fallida:**
1. Foto de la fachada antes de retirarse
(Nota: Kosmo no permite agregar notas del driver en entregas fallidas)

CLAVES DE ERROR DISPONIBLES:
- falta_fachada: Falta foto de fachada del domicilio
- guia_no_visible: Guía de envío no visible o ilegible
- foto_borrosa: Foto borrosa o sin foco
- sin_foto_receptor: Falta foto del receptor o tercero
- paquete_fuera_frame: Paquete fuera de encuadre o cortado
- falta_whatsapp: Falta captura de WhatsApp o SMS

RESPONDE SIEMPRE en formato JSON con esta estructura exacta:
{
  "photos_analysis": [
    {
      "photo_index": 0,
      "photo_type": "fachada|paquete_guia|receptor|llamadas|firma|otro",
      "description": "breve descripción de lo que se ve",
      "guide_number_visible": true/false,
      "guide_number_text": "texto OCR de guía si es visible o null",
      "timestamp_visible": true/false,
      "quality": "buena|aceptable|deficiente",
      "quality_notes": "notas sobre calidad"
    }
  ],
  "delivery_type_detected": "exitosa|terceros|fallida",
  "criteria_met": {
    "foto_fachada": true/false,
    "foto_paquete_guia": true/false,
    "guia_legible": true/false,
    "foto_receptor": true/false,
    "nota_driver": true/false,
    "captura_llamadas": true/false,
    "min_2_llamadas": true/false
  },
  "overall_score": 0-100,
  "confidence": 0.0-1.0,
  "errors": ["clave_error_1", "clave_error_2"],
  "severity": {"clave_error_1": "critical", "clave_error_2": "warning"},
  "missing_items": ["lista de items faltantes según criterios Cubbo"],
  "alerts": ["alertas importantes"],
  "feedback": "Explicación concisa en español de los hallazgos principales"
}"""


def calculate_evidence_score_rules(package: dict, has_incident: bool = False) -> dict | None:
    """Rule-based evidence scoring (fallback when AI is unavailable)."""
    status = package.get("status")
    if status not in ("delivered", "failed"):
        return None

    proof_count = package.get("kosmo_proof_count") or 0
    driver_note = package.get("kosmo_driver_note") or ""
    has_driver_note = bool(driver_note.strip())
    now_iso = datetime.now(timezone.utc).isoformat()

    if status == "delivered":
        note_lower = driver_note.lower()
        is_third_party = any(kw in note_lower for kw in THIRD_PARTY_KEYWORDS)
        evidence_type = "terceros" if is_third_party else "exitosa"

        missing_items = []
        if proof_count < 1:
            missing_items.append("Foto de fachada")
        if proof_count < 2:
            missing_items.append("Foto de paquete con guía")
        if proof_count < 3:
            missing_items.append("Foto de receptor")

        if evidence_type == "exitosa":
            if proof_count >= 3:
                score = 100
            elif proof_count == 2:
                score = 70
            elif proof_count == 1:
                score = 40
            else:
                score = 0
        else:
            if not has_driver_note:
                missing_items.append("Nota de confirmación al cliente")
            if proof_count >= 3 and has_driver_note:
                score = 100
            elif proof_count >= 3 and not has_driver_note:
                score = 70
            else:
                score = 50

        return {
            "evidence_type": evidence_type,
            "evidence_score": score,
            "evidence_detail": {
                "proof_count": proof_count,
                "has_driver_note": has_driver_note,
                "incident_registered": has_incident,
                "missing_items": missing_items,
            },
            "evidence_evaluated_at": now_iso,
            "evidence_method": "rules",
        }

    elif status == "failed":
        evidence_type = "fallida"
        missing_items = []
        has_photo = proof_count >= 1

        if not has_photo:
            missing_items.append("Foto de fachada antes de retirarse")

        # Kosmo does not allow driver notes on failed deliveries
        # Only photo evidence is evaluated
        if has_photo:
            score = 100
        else:
            score = 0

        return {
            "evidence_type": evidence_type,
            "evidence_score": score,
            "evidence_detail": {
                "proof_count": proof_count,
                "has_driver_note": has_driver_note,
                "incident_registered": has_incident,
                "missing_items": missing_items,
            },
            "evidence_evaluated_at": now_iso,
            "evidence_method": "rules",
        }

    return None


# Keep backward-compatible name
def calculate_evidence_score(package: dict, has_incident: bool = False) -> dict | None:
    return calculate_evidence_score_rules(package, has_incident)


async def _download_image_as_base64(url: str) -> Optional[str]:
    """Download an image from URL and return base64 string."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) > 100:
                return base64.b64encode(resp.content).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to download image: {e}")
    return None


async def evaluate_single_package_ai(
    package: dict,
    has_incident: bool = False,
) -> dict:
    """
    Evaluate a single package's evidence using OpenAI Vision (GPT-4o).
    Falls back to rule-based scoring if AI evaluation fails.
    """
    status = package.get("status")
    if status not in ("delivered", "failed"):
        return {"error": "Package status must be delivered or failed"}

    proof_urls = package.get("kosmo_proof_urls") or []
    driver_note = package.get("kosmo_driver_note") or ""
    tracking = package.get("tracking_number") or package.get("order_reference_id") or "N/A"
    now_iso = datetime.now(timezone.utc).isoformat()

    # If no proof URLs, use rule-based only
    if not proof_urls:
        result = calculate_evidence_score_rules(package, has_incident)
        if result:
            result["evidence_method"] = "rules"
            result["ai_evaluation"] = None
        return result or {}

    # Download images concurrently
    tasks = [_download_image_as_base64(url) for url in proof_urls[:6]]
    base64_images = await asyncio.gather(*tasks)
    valid_images = [img for img in base64_images if img]

    if not valid_images:
        logger.warning(f"No images could be downloaded for package {tracking}, falling back to rules")
        result = calculate_evidence_score_rules(package, has_incident)
        if result:
            result["evidence_method"] = "rules"
            result["ai_evaluation"] = {"error": "No se pudieron descargar las imágenes (URLs expiradas)"}
        return result or {}

    # Build AI evaluation using emergentintegrations
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise ValueError("EMERGENT_LLM_KEY not configured")

        chat = LlmChat(
            api_key=api_key,
            session_id=f"evidence-eval-{uuid.uuid4().hex[:8]}",
            system_message=CUBBO_SYSTEM_PROMPT,
        )
        chat.with_model("anthropic", "claude-sonnet-4-5-20250929")

        # Build message with images
        file_contents = [ImageContent(image_base64=img) for img in valid_images]

        context = f"Paquete: {tracking}\nEstatus: {'Entregado' if status == 'delivered' else 'Fallido'}\n"
        if driver_note:
            context += f"Nota del driver: {driver_note}\n"
        context += f"Total de fotos: {len(valid_images)}\n"
        context += "\nAnaliza las fotos de evidencia adjuntas y responde en JSON."

        user_msg = UserMessage(text=context, file_contents=file_contents)
        response_text = await chat.send_message(user_msg)

        # Log token usage (non-blocking)
        try:
            from token_logger import log_token_usage
            await log_token_usage(
                db=_get_db(),
                entregable="evaluacion",
                modelo="claude-sonnet-4-5",
                referencia=tracking,
                input_text=context,
                output_text=response_text or "",
                system_prompt=CUBBO_SYSTEM_PROMPT,
                journey_id=package.get("journey_id"),
                guide=tracking,
                client_id=package.get("client_id"),
            )
        except Exception as log_err:
            logger.debug(f"Token log skipped: {log_err}")

        # Parse JSON from response
        ai_result = _parse_ai_response(response_text)

        if ai_result:
            note_lower = driver_note.lower()
            is_third_party = any(kw in note_lower for kw in THIRD_PARTY_KEYWORDS)

            if status == "delivered":
                evidence_type = ai_result.get("delivery_type_detected", "terceros" if is_third_party else "exitosa")
            else:
                evidence_type = "fallida"

            score = ai_result.get("overall_score", 0)
            missing = ai_result.get("missing_items", [])
            alerts = ai_result.get("alerts", [])
            confidence = ai_result.get("confidence", 0.5)
            ia_errors = ai_result.get("errors", [])
            ia_severity = ai_result.get("severity", {})
            feedback = ai_result.get("feedback", ai_result.get("ai_observations", ""))

            return {
                "evidence_type": evidence_type,
                "evidence_score": score,
                "ia_confidence": confidence,
                "ia_errors": ia_errors,
                "ia_severity": ia_severity,
                "ia_feedback": feedback,
                "evidence_detail": {
                    "proof_count": len(proof_urls),
                    "has_driver_note": bool(driver_note.strip()),
                    "incident_registered": has_incident,
                    "missing_items": missing,
                    "alerts": alerts,
                    "photos_analysis": ai_result.get("photos_analysis", []),
                    "criteria_met": ai_result.get("criteria_met", {}),
                    "ai_observations": feedback,
                },
                "evidence_evaluated_at": now_iso,
                "evidence_method": "ai",
            }
        else:
            logger.warning(f"AI response could not be parsed for {tracking}, falling back to rules")
            result = calculate_evidence_score_rules(package, has_incident)
            if result:
                result["evidence_method"] = "rules"
                result["ai_evaluation"] = {"error": "Respuesta de IA no pudo ser procesada"}
            return result or {}

    except Exception as e:
        logger.error(f"AI evaluation failed for {tracking}: {e}")
        result = calculate_evidence_score_rules(package, has_incident)
        if result:
            result["evidence_method"] = "rules"
            result["ai_evaluation"] = {"error": str(e)}
        return result or {}


def _parse_ai_response(text: str) -> Optional[dict]:
    """Parse JSON from AI response text, handling markdown code blocks."""
    if not text:
        return None
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding JSON object in text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def evaluate_packages_for_journey(db: AsyncIOMotorDatabase, journey_id: str, use_ai: bool = False):
    """Evaluate evidence scores for all delivered/failed packages in a journey."""
    packages = await db.packages.find(
        {"journey_id": journey_id, "status": {"$in": ["delivered", "failed"]}},
        {"_id": 0},
    ).to_list(5000)

    incidents = await db.incidents.find(
        {"journey_id": journey_id},
        {"_id": 0, "tracking_number": 1},
    ).to_list(5000)
    incident_tracking_numbers = {
        i.get("tracking_number", "").strip().lower()
        for i in incidents
        if i.get("tracking_number")
    }

    for pkg in packages:
        tn = (pkg.get("tracking_number") or "").strip().lower()
        has_incident = tn in incident_tracking_numbers if tn else False

        if use_ai:
            result = await evaluate_single_package_ai(pkg, has_incident)
        else:
            result = calculate_evidence_score_rules(pkg, has_incident)

        if result and "error" not in result:
            await db.packages.update_one(
                {"id": pkg["id"]},
                {"$set": result},
            )


async def evaluate_single_package_for_journey(
    db: AsyncIOMotorDatabase,
    journey_id: str,
    guide: str,
    use_ai: bool = True,
) -> dict:
    """Evaluate evidence for a single package in a journey, identified by guide/order_reference_id."""
    pkg = await db.packages.find_one(
        {
            "journey_id": journey_id,
            "$or": [
                {"order_reference_id": guide},
                {"tracking_number": guide},
            ],
        },
        {"_id": 0},
    )
    if not pkg:
        return {"error": "Paquete no encontrado"}

    if pkg.get("status") not in ("delivered", "failed"):
        return {"error": "Solo se evalúan paquetes entregados o fallidos"}

    incident = await db.incidents.find_one(
        {"journey_id": journey_id, "tracking_number": {"$regex": guide, "$options": "i"}},
        {"_id": 0},
    )
    has_incident = incident is not None

    if use_ai:
        result = await evaluate_single_package_ai(pkg, has_incident)
    else:
        result = calculate_evidence_score_rules(pkg, has_incident)

    if result and "error" not in result:
        await db.packages.update_one(
            {"id": pkg["id"]},
            {"$set": result},
        )
        result["package_id"] = pkg["id"]
        result["tracking_number"] = pkg.get("tracking_number")
        result["order_reference_id"] = pkg.get("order_reference_id")

    return result


async def evaluate_packages_by_ids(db: AsyncIOMotorDatabase, package_ids: list, journey_ids: set = None):
    """Evaluate evidence for specific packages (used after sync) - rule-based for speed."""
    if not package_ids:
        return

    packages = await db.packages.find(
        {"id": {"$in": package_ids}, "status": {"$in": ["delivered", "failed"]}},
        {"_id": 0},
    ).to_list(5000)

    relevant_journey_ids = journey_ids or {p.get("journey_id") for p in packages if p.get("journey_id")}

    incidents = await db.incidents.find(
        {"journey_id": {"$in": list(relevant_journey_ids)}},
        {"_id": 0, "tracking_number": 1},
    ).to_list(5000)
    incident_tracking_numbers = {
        i.get("tracking_number", "").strip().lower()
        for i in incidents
        if i.get("tracking_number")
    }

    for pkg in packages:
        tn = (pkg.get("tracking_number") or "").strip().lower()
        has_incident = tn in incident_tracking_numbers if tn else False
        result = calculate_evidence_score_rules(pkg, has_incident)
        if result:
            await db.packages.update_one(
                {"id": pkg["id"]},
                {"$set": result},
            )
