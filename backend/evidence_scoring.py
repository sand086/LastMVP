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
from datetime import datetime, timezone, timedelta
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
- falta_whatsapp: Falta captura de WhatsApp o SMS"""

AI_RESPONSE_FORMAT = """

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


def _score_delivered(proof_count: int, driver_note: str, has_incident: bool) -> dict:
    """Score delivered packages based on proof count and driver notes."""
    note_lower = driver_note.lower()
    is_third_party = any(kw in note_lower for kw in THIRD_PARTY_KEYWORDS)
    evidence_type = "terceros" if is_third_party else "exitosa"
    has_driver_note = bool(driver_note.strip())

    missing_items = []
    if proof_count < 1:
        missing_items.append("Foto de fachada")
    if proof_count < 2:
        missing_items.append("Foto de paquete con guía")
    if proof_count < 3:
        missing_items.append("Foto de receptor")

    # Scoring based on evidence type
    if evidence_type == "exitosa":
        score_map = {0: 0, 1: 40, 2: 70}
        score = score_map.get(proof_count, 100)
    else:
        if not has_driver_note:
            missing_items.append("Nota de confirmación al cliente")
        if proof_count >= 3 and has_driver_note:
            score = 100
        elif proof_count >= 3:
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
        "evidence_evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_method": "rules",
    }


def _score_failed(proof_count: int, driver_note: str, has_incident: bool) -> dict:
    """Score failed delivery packages."""
    missing_items = []
    if proof_count < 1:
        missing_items.append("Foto de fachada antes de retirarse")

    return {
        "evidence_type": "fallida",
        "evidence_score": 100 if proof_count >= 1 else 0,
        "evidence_detail": {
            "proof_count": proof_count,
            "has_driver_note": bool(driver_note.strip()),
            "incident_registered": has_incident,
            "missing_items": missing_items,
        },
        "evidence_evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_method": "rules",
    }


def calculate_evidence_score_rules(package: dict, has_incident: bool = False) -> dict | None:
    """Rule-based evidence scoring (fallback when AI is unavailable)."""
    status = package.get("status")
    if status not in ("delivered", "failed"):
        return None

    proof_count = package.get("kosmo_proof_count") or 0
    driver_note = package.get("kosmo_driver_note") or ""

    if status == "delivered":
        return _score_delivered(proof_count, driver_note, has_incident)
    return _score_failed(proof_count, driver_note, has_incident)


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


def _rules_fallback(package: dict, has_incident: bool, error_msg: str = None) -> dict:
    """Fall back to rule-based scoring with optional error info."""
    result = calculate_evidence_score_rules(package, has_incident)
    if result:
        result["evidence_method"] = "rules"
        if error_msg:
            result["ai_evaluation"] = {"error": error_msg}
        else:
            result["ai_evaluation"] = None
    return result or {}


def _build_ai_result(ai_result: dict, package: dict, has_incident: bool, proof_urls: list, driver_note: str) -> dict:
    """Build the return dict from a parsed AI response."""
    status = package.get("status")
    note_lower = driver_note.lower()
    is_third_party = any(kw in note_lower for kw in THIRD_PARTY_KEYWORDS)

    if status == "delivered":
        evidence_type = ai_result.get("delivery_type_detected", "terceros" if is_third_party else "exitosa")
    else:
        evidence_type = "fallida"

    feedback = ai_result.get("feedback", ai_result.get("ai_observations", ""))

    return {
        "evidence_type": evidence_type,
        "evidence_score": ai_result.get("overall_score", 0),
        "ia_confidence": ai_result.get("confidence", 0.5),
        "ia_errors": ai_result.get("errors", []),
        "ia_severity": ai_result.get("severity", {}),
        "ia_feedback": feedback,
        "evidence_detail": {
            "proof_count": len(proof_urls),
            "has_driver_note": bool(driver_note.strip()),
            "incident_registered": has_incident,
            "missing_items": ai_result.get("missing_items", []),
            "alerts": ai_result.get("alerts", []),
            "photos_analysis": ai_result.get("photos_analysis", []),
            "criteria_met": ai_result.get("criteria_met", {}),
            "ai_observations": feedback,
        },
        "evidence_evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_method": "ai",
    }


async def evaluate_single_package_ai(
    package: dict,
    has_incident: bool = False,
) -> dict:
    """
    Evaluate a single package's evidence using AI Vision.
    Falls back to rule-based scoring if AI evaluation fails.
    """
    status = package.get("status")
    if status not in ("delivered", "failed"):
        return {"error": "Package status must be delivered or failed"}

    proof_urls = package.get("kosmo_proof_urls") or []
    driver_note = package.get("kosmo_driver_note") or ""
    tracking = package.get("tracking_number") or package.get("order_reference_id") or "N/A"

    if not proof_urls:
        return _rules_fallback(package, has_incident)

    # Download images concurrently
    tasks = [_download_image_as_base64(url) for url in proof_urls[:6]]
    base64_images = await asyncio.gather(*tasks)
    valid_images = [img for img in base64_images if img]

    if not valid_images:
        logger.warning(f"No images could be downloaded for package {tracking}, falling back to rules")
        return _rules_fallback(package, has_incident, "No se pudieron descargar las imágenes (URLs expiradas)")

    try:
        ai_result = await _call_ai_vision(valid_images, tracking, status, driver_note)

        if ai_result:
            return _build_ai_result(ai_result, package, has_incident, proof_urls, driver_note)

        logger.warning(f"AI response could not be parsed for {tracking}, falling back to rules")
        return _rules_fallback(package, has_incident, "Respuesta de IA no pudo ser procesada")

    except Exception as e:
        logger.error(f"AI evaluation failed for {tracking}: {e}")
        return _rules_fallback(package, has_incident, str(e))


async def _get_system_prompt() -> str:
    """Read custom system prompt from quality criteria config, falling back to default."""
    base_prompt = CUBBO_SYSTEM_PROMPT
    try:
        db = _get_db()
        ia_config_doc = await db.config.find_one({"key": "ia_config"}, {"_id": 0})
        if ia_config_doc:
            custom_prompt = ia_config_doc.get("value", {}).get("system_prompt", "")
            if custom_prompt and custom_prompt.strip():
                base_prompt = custom_prompt.strip()
                logger.info(f"Using custom system prompt from quality criteria config ({len(base_prompt)} chars)")
    except Exception as e:
        logger.warning(f"Could not read custom system prompt: {e}")
    return base_prompt + AI_RESPONSE_FORMAT


async def _get_training_context() -> str:
    """Fetch recent incorrect AI evaluations as few-shot calibration examples."""
    try:
        db = _get_db()
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        recent_samples = await db.training_samples.find(
            {"labeled_at": {"$gte": thirty_days_ago}, "ai_evaluation_incorrect": True},
            {"_id": 0, "tracking_number": 1, "ia_errors": 1, "original_ai_score": 1,
             "adjusted_score": 1, "reviewer_note": 1, "decision": 1, "proof_count": 1},
        ).sort("labeled_at", -1).to_list(5)

        if recent_samples:
            examples = [
                f"- Guía {s.get('tracking_number','?')}: IA dio {s.get('original_ai_score',0)}, revisión humana: {s.get('decision','?')} (score ajustado: {s.get('adjusted_score','N/A')}). Nota: {s.get('reviewer_note','')}"
                for s in recent_samples
            ]
            return "\n\nCALIBRACIÓN POR REVISIÓN HUMANA (ejemplos recientes donde la IA se equivocó):\n" + "\n".join(examples) + "\nConsidera estos casos al evaluar para calibrar mejor tu criterio.\n"
    except Exception as e:
        logger.debug(f"Training samples fetch skipped: {e}")
    return ""


def _build_user_context(tracking: str, status: str, driver_note: str, image_count: int, training_context: str) -> str:
    """Build the user message context string for AI evaluation."""
    context = f"Paquete: {tracking}\nEstatus: {'Entregado' if status == 'delivered' else 'Fallido'}\n"
    if driver_note:
        context += f"Nota del driver: {driver_note}\n"
    context += f"Total de fotos: {image_count}\n"
    if training_context:
        context += training_context
    context += "\nAnaliza las fotos de evidencia adjuntas y responde en JSON."
    return context


async def _log_ai_token_usage(tracking: str, context: str, response_text: str, system_prompt: str) -> None:
    """Log AI token usage (non-blocking, swallows errors)."""
    try:
        from token_logger import log_token_usage
        await log_token_usage(
            db=_get_db(),
            entregable="evaluacion",
            modelo="claude-sonnet-4-5",
            referencia=tracking,
            input_text=context,
            output_text=response_text or "",
            system_prompt=system_prompt,
        )
    except Exception as log_err:
        logger.debug(f"Token log skipped: {log_err}")


async def _call_ai_vision(valid_images: list, tracking: str, status: str, driver_note: str) -> Optional[dict]:
    """Send images to AI Vision and return parsed result."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("EMERGENT_LLM_KEY not configured")

    system_prompt = await _get_system_prompt()
    training_context = await _get_training_context()

    chat = LlmChat(
        api_key=api_key,
        session_id=f"evidence-eval-{uuid.uuid4().hex[:8]}",
        system_message=system_prompt,
    )
    chat.with_model("anthropic", "claude-sonnet-4-5-20250929")

    context = _build_user_context(tracking, status, driver_note, len(valid_images), training_context)
    file_contents = [ImageContent(image_base64=img) for img in valid_images]
    user_msg = UserMessage(text=context, file_contents=file_contents)
    response_text = await chat.send_message(user_msg)

    await _log_ai_token_usage(tracking, context, response_text, system_prompt)

    return _parse_ai_response(response_text)


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


# Global semaphore to limit concurrent AI evaluations and prevent event loop starvation
_ai_eval_semaphore = asyncio.Semaphore(2)  # Max 2 concurrent LLM calls
_AI_BATCH_SIZE = 3  # Process N packages per batch
_AI_BATCH_DELAY = 0.1  # Seconds to yield event loop between batches

# Thread pool for isolating heavy AI work from the main event loop
from concurrent.futures import ThreadPoolExecutor
_ai_thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-eval")

# In-memory AI evaluation status tracker per journey
_ai_eval_status: dict = {}


def get_ai_eval_status(journey_id: str) -> dict:
    """Get current AI evaluation status for a journey."""
    return _ai_eval_status.get(journey_id, {"status": "idle"})


def _set_ai_eval_status(journey_id: str, status: str, total: int = 0, evaluated: int = 0, errors: int = 0):
    """Update AI evaluation status for a journey."""
    _ai_eval_status[journey_id] = {
        "status": status,
        "total": total,
        "evaluated": evaluated,
        "errors": errors,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _run_ai_eval_sync(journey_id: str, packages: list, incident_tracking_numbers: set):
    """Run AI evaluation in a separate thread with its own event loop.
    This completely isolates LLM calls from the main event loop."""
    _set_ai_eval_status(journey_id, "running", total=len(packages))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _evaluate_packages_ai_internal(journey_id, packages, incident_tracking_numbers)
        )
        status = get_ai_eval_status(journey_id)
        _set_ai_eval_status(journey_id, "completed", total=status["total"], evaluated=status["evaluated"], errors=status["errors"])
    except Exception as e:
        logger.error(f"AI eval thread error for journey {journey_id}: {e}")
        status = get_ai_eval_status(journey_id)
        _set_ai_eval_status(journey_id, "error", total=status["total"], evaluated=status["evaluated"], errors=status["errors"])
    finally:
        loop.close()


async def _evaluate_packages_ai_internal(journey_id: str, packages: list, incident_tracking_numbers: set):
    """Internal async function that runs in a separate thread's event loop."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import os

    # Create a NEW MongoDB connection for this thread's event loop
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    total = len(packages)
    evaluated = 0
    eval_errors = 0
    sem = asyncio.Semaphore(2)

    async def _eval_one(pkg):
        nonlocal evaluated, eval_errors
        tn = (pkg.get("tracking_number") or "").strip().lower()
        has_incident = tn in incident_tracking_numbers if tn else False
        async with sem:
            result = await evaluate_single_package_ai(pkg, has_incident)
        if result and "error" not in result:
            await db.packages.update_one({"id": pkg["id"]}, {"$set": result})
        elif result and "error" in result:
            eval_errors += 1
        evaluated += 1
        _set_ai_eval_status(journey_id, "running", total=total, evaluated=evaluated, errors=eval_errors)

    for i in range(0, total, _AI_BATCH_SIZE):
        batch = packages[i:i + _AI_BATCH_SIZE]
        await asyncio.gather(*[_eval_one(pkg) for pkg in batch])
        await asyncio.sleep(_AI_BATCH_DELAY)
        if evaluated % 6 == 0 and evaluated > 0:
            logger.info(f"AI eval progress: {evaluated}/{total} for journey {journey_id}")

    logger.info(f"AI evaluation completed for journey {journey_id}: {evaluated}/{total}")
    client.close()


async def evaluate_packages_for_journey(db: AsyncIOMotorDatabase, journey_id: str, use_ai: bool = False):
    """Evaluate evidence scores for all delivered/failed packages in a journey.
    AI mode runs in a separate thread to avoid blocking the main event loop."""
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

    if not use_ai:
        # Rule-based: fast, run inline
        for pkg in packages:
            tn = (pkg.get("tracking_number") or "").strip().lower()
            has_incident = tn in incident_tracking_numbers if tn else False
            result = calculate_evidence_score_rules(pkg, has_incident)
            if result and "error" not in result:
                await db.packages.update_one({"id": pkg["id"]}, {"$set": result})
        return

    # AI mode: offload to a separate thread with its own event loop
    total = len(packages)
    logger.info(f"AI evaluation dispatched to background thread for journey {journey_id}: {total} packages")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        _ai_thread_pool,
        _run_ai_eval_sync,
        journey_id,
        packages,
        incident_tracking_numbers,
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
    """Evaluate evidence for specific packages (used after sync) - rule-based for speed.
    IMPORTANT: Preserves AI evaluations — only applies rules to packages NOT evaluated by AI.
    """
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
        # Skip packages already evaluated by AI — preserve their detailed analysis
        if pkg.get("evidence_method") == "ai" and pkg.get("evidence_detail"):
            continue

        tn = (pkg.get("tracking_number") or "").strip().lower()
        has_incident = tn in incident_tracking_numbers if tn else False
        result = calculate_evidence_score_rules(pkg, has_incident)
        if result:
            await db.packages.update_one(
                {"id": pkg["id"]},
                {"$set": result},
            )
