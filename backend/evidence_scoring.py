"""
Evidence Quality Scoring Module
Based on Cubbo delivery evidence standards.
Evaluates package evidence quality (photos, driver notes, incidents).
"""

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

THIRD_PARTY_KEYWORDS = [
    "vecino", "vigilante", "tercero", "familiar", "portero",
    "guardia", "recepción", "conserje", "seguridad", "caseta",
]


def calculate_evidence_score(package: dict, has_incident: bool = False) -> dict | None:
    """
    Evaluate evidence quality for a single package based on Cubbo standard.
    Returns dict with evidence_type, evidence_score, evidence_detail, evidence_evaluated_at.
    Returns None if package status is not delivered or failed.
    """
    status = package.get("status")
    if status not in ("delivered", "failed"):
        return None

    proof_count = package.get("kosmo_proof_count") or 0
    driver_note = package.get("kosmo_driver_note") or ""
    has_driver_note = bool(driver_note.strip())
    now_iso = datetime.now(timezone.utc).isoformat()

    if status == "delivered":
        # Determine if delivery was to third party
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
            # terceros
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
        }

    elif status == "failed":
        evidence_type = "fallida"
        missing_items = []

        if proof_count == 0:
            missing_items.append("Foto de fachada antes de retirarse")

        if proof_count >= 1:
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
        }

    return None


async def evaluate_packages_for_journey(db: AsyncIOMotorDatabase, journey_id: str):
    """Evaluate evidence scores for all delivered/failed packages in a journey."""
    packages = await db.packages.find(
        {"journey_id": journey_id, "status": {"$in": ["delivered", "failed"]}},
        {"_id": 0},
    ).to_list(5000)

    # Get all incident tracking numbers for this journey
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
        result = calculate_evidence_score(pkg, has_incident)
        if result:
            await db.packages.update_one(
                {"id": pkg["id"]},
                {"$set": result},
            )


async def evaluate_packages_by_ids(db: AsyncIOMotorDatabase, package_ids: list, journey_ids: set = None):
    """Evaluate evidence for specific packages (used after sync)."""
    if not package_ids:
        return

    packages = await db.packages.find(
        {"id": {"$in": package_ids}, "status": {"$in": ["delivered", "failed"]}},
        {"_id": 0},
    ).to_list(5000)

    # Get all relevant journey_ids
    relevant_journey_ids = journey_ids or {p.get("journey_id") for p in packages if p.get("journey_id")}

    # Get all incident tracking numbers for relevant journeys
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
        result = calculate_evidence_score(pkg, has_incident)
        if result:
            await db.packages.update_one(
                {"id": pkg["id"]},
                {"$set": result},
            )
