"""
Routal journey sync (R00C / iter64).

Pulls a journey's stops from Routal API (ground truth) and reconciles them onto
LastMile packages. Used when webhook deliveries are missed, retried, or arrived
without evidence (status only).

Policy:
  - status='completed'  → package.status='delivered', delivered_at=report.created_at,
                          proof URLs (proxified), driver note, signature.
  - status='failed' / 'incomplete' / 'canceled' → package.status='failed' + fail_reason.
  - status='pending'    → no-op (preserve any existing local state).

Idempotent: re-runs do not duplicate evidence and only update changed fields.
Image URLs are proxified through `/api/integrations/routal/image/...` to avoid
exposing the Routal API key in the browser.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_proxy_image_url(api_base: str, client_id: str, report_id: str, image_id: str) -> str:
    """Internal URL the browser will hit. Backend proxies the bytes from Routal
    using the stored client API key (never exposed to the frontend).
    """
    return f"{api_base.rstrip('/')}/api/integrations/routal/image/{client_id}/{report_id}/{image_id}"


def _extract_evidence(report: dict, client_id: str, api_base: str) -> dict:
    """Pull evidence fields from a Routal `service_report_*` doc."""
    images = report.get("images") or []
    proof_urls = []
    for img in images:
        if isinstance(img, dict) and img.get("id"):
            proof_urls.append(_build_proxy_image_url(api_base, client_id, report["id"], img["id"]))
    sig = report.get("signature") or {}
    signature_url = None
    if isinstance(sig, dict) and sig.get("id"):
        # Signature uses the same image-by-id endpoint per Routal v3 spec
        signature_url = _build_proxy_image_url(api_base, client_id, report["id"], sig["id"]) + "?kind=signature"
    return {
        "proof_urls": proof_urls,
        "proof_count": len(proof_urls),
        "driver_note": report.get("comments") or "",
        "signature_url": signature_url,
        "report_id": report["id"],
        "completed_at": report.get("created_at"),
        "report_type": report.get("type"),
    }


async def sync_journey_from_routal(db, journey_id: str, api_base: str) -> dict:
    """Reconcile a single journey against Routal API. Returns summary dict."""
    from services.integration_service import IntegrationService

    journey = await db.journeys.find_one(
        {"id": journey_id},
        {"_id": 0, "id": 1, "client_id": 1, "routal_plan_id": 1, "source": 1, "status": 1, "date": 1},
    )
    if not journey:
        return {"ok": False, "error": "journey not found", "journey_id": journey_id}
    if journey.get("source") != "routal":
        return {"ok": False, "error": "journey is not from routal", "source": journey.get("source")}
    plan_id = journey.get("routal_plan_id")
    if not plan_id:
        return {"ok": False, "error": "journey has no routal_plan_id"}
    client_id = journey["client_id"]

    svc = IntegrationService(db)
    rc = await svc.get_routal_client(client_id)
    if not rc:
        return {"ok": False, "error": "routal integration inactive for client"}

    try:
        try:
            detail = await rc.get_plan(plan_id)
        except Exception as e:
            logger.error(f"[routal-sync] get_plan {plan_id} failed: {e}")
            return {"ok": False, "error": f"routal api error: {str(e)[:200]}"}

        stops_by_id = {s["id"]: s for s in (detail.get("stops") or []) if s.get("id")}

        # Index packages by routal_service_id (was set at journey creation time)
        packages = await db.packages.find(
            {"journey_id": journey_id, "client_id": client_id},
            {"_id": 0, "id": 1, "routal_service_id": 1, "status": 1, "kosmo_proof_count": 1,
             "recipient_name": 1, "address": 1, "tracking_number": 1, "order_reference_id": 1},
        ).to_list(length=10000)

        # If journey doesn't have routal_plan_label yet, persist it
        plan_label = detail.get("label")
        await db.journeys.update_one(
            {"id": journey_id, "client_id": client_id, "routal_plan_label": {"$in": [None, ""]}},
            {"$set": {"routal_plan_label": plan_label}} if plan_label else {"$set": {}},
        )

        from workers.routal_event_processor import map_routal_stop_to_pkg_fields
        from utils.pii import encrypt_pkg_pii, ENC_PREFIX as _ENC_PREFIX

        delivered = 0
        failed = 0
        pending = 0
        unchanged = 0
        no_match = 0
        recipient_filled = 0

        def _build_recipient_update(stop, pkg):
            """Returns dict with PII-encrypted recipient fields if missing locally."""
            mapped = map_routal_stop_to_pkg_fields(stop)
            ru = {}
            current_recipient = pkg.get("recipient_name") or ""
            if mapped.get("recipient_name") and not current_recipient.startswith(_ENC_PREFIX) and not current_recipient:
                ru["recipient_name"] = mapped["recipient_name"]
            current_addr = pkg.get("address") or ""
            if mapped.get("address") and not current_addr.startswith(_ENC_PREFIX) and not current_addr:
                ru["address"] = mapped["address"]
            if not pkg.get("order_reference_id") and mapped.get("order_reference_id"):
                ru["order_reference_id"] = mapped["order_reference_id"]
            if ru:
                pii_fields = {k: v for k, v in ru.items() if k in ("recipient_name", "address", "recipient_phone")}
                if pii_fields:
                    encrypt_pkg_pii(pii_fields)
                    ru.update(pii_fields)
            return ru

        for pkg in packages:
            svc_id = pkg.get("routal_service_id")
            if not svc_id or svc_id not in stops_by_id:
                no_match += 1
                continue
            stop = stops_by_id[svc_id]
            stop_status = (stop.get("status") or "").lower()

            if stop_status == "completed":
                # Pick first matching report (Routal usually emits one per stop)
                reports = stop.get("reports") or []
                completed_report = next(
                    (r for r in reports if (r.get("type") or "").endswith("_completed")),
                    reports[0] if reports else None,
                )
                evidence = _extract_evidence(completed_report, client_id, api_base) if completed_report else {}
                update = {
                    "status": "delivered",
                    "delivered_at": evidence.get("completed_at") or stop.get("updated_at") or _now_iso(),
                    "updated_at": _now_iso(),
                    "routal_synced_at": _now_iso(),
                }
                if evidence:
                    update["kosmo_proof_urls"] = evidence["proof_urls"]
                    update["kosmo_proof_count"] = evidence["proof_count"]
                    if evidence.get("driver_note"):
                        update["kosmo_driver_note"] = evidence["driver_note"]
                    if evidence.get("signature_url"):
                        update["routal_signature_url"] = evidence["signature_url"]
                    if evidence.get("report_id"):
                        update["routal_report_id"] = evidence["report_id"]
                ru = _build_recipient_update(stop, pkg)
                update.update(ru)
                if ru:
                    recipient_filled += 1
                if (
                    pkg.get("status") == "delivered"
                    and pkg.get("kosmo_proof_count") == evidence.get("proof_count")
                    and not ru
                ):
                    unchanged += 1
                    continue
                await db.packages.update_one(
                    {"id": pkg["id"], "client_id": client_id},
                    {"$set": update},
                )
                delivered += 1
            elif stop_status in ("failed", "incomplete", "canceled", "cancelled"):
                reports = stop.get("reports") or []
                failed_report = next(
                    (r for r in reports if (r.get("type") or "").endswith(("_failed", "_incomplete", "_canceled"))),
                    reports[0] if reports else None,
                )
                evidence = _extract_evidence(failed_report, client_id, api_base) if failed_report else {}
                ru = _build_recipient_update(stop, pkg)
                if pkg.get("status") == "failed" and not ru:
                    unchanged += 1
                    continue
                update = {
                    "status": "failed",
                    "failed_at": evidence.get("completed_at") or stop.get("updated_at") or _now_iso(),
                    "fail_reason": evidence.get("driver_note") or "Reportado fallido por Routal",
                    "updated_at": _now_iso(),
                    "routal_synced_at": _now_iso(),
                }
                if evidence:
                    update["kosmo_proof_urls"] = evidence["proof_urls"]
                    update["kosmo_proof_count"] = evidence["proof_count"]
                update.update(ru)
                if ru:
                    recipient_filled += 1
                await db.packages.update_one(
                    {"id": pkg["id"], "client_id": client_id},
                    {"$set": update},
                )
                failed += 1
            else:
                pending += 1
                # Even for pending stops, fill in destination if empty
                ru = _build_recipient_update(stop, pkg)
                if ru:
                    ru["routal_synced_at"] = _now_iso()
                    await db.packages.update_one(
                        {"id": pkg["id"], "client_id": client_id},
                        {"$set": ru},
                    )
                    recipient_filled += 1

        # Recalculate journey counters
        agg = await db.packages.aggregate([
            {"$match": {"journey_id": journey_id, "client_id": client_id}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ]).to_list(length=20)
        counts = {row["_id"]: row["n"] for row in agg}
        await db.journeys.update_one(
            {"id": journey_id},
            {"$set": {
                "packages_delivered": counts.get("delivered", 0),
                "packages_failed": counts.get("failed", 0),
                "routal_synced_at": _now_iso(),
                "updated_at": _now_iso(),
            }},
        )

        return {
            "ok": True,
            "journey_id": journey_id,
            "plan_id": plan_id,
            "plan_label": plan_label,
            "stops_in_routal": len(stops_by_id),
            "packages_in_journey": len(packages),
            "delivered_synced": delivered,
            "failed_synced": failed,
            "still_pending": pending,
            "unchanged": unchanged,
            "no_routal_match": no_match,
            "recipient_filled": recipient_filled,
        }
    finally:
        try:
            await rc.aclose()
        except Exception:
            pass


async def proxy_routal_image(db, client_id: str, report_id: str, image_id: str) -> Optional[tuple]:
    """Fetches a Routal report image as bytes using the client's API key.
    Returns (content_bytes, content_type) or None if unavailable.
    """
    from services.integration_service import IntegrationService
    svc = IntegrationService(db)
    rc = await svc.get_routal_client(client_id)
    if not rc:
        return None
    try:
        # Routal v3 endpoint serves image binary at /v3/stop/report/{report_id}/image/{image_id}
        url = f"{rc._base_url}/v3/stop/report/{report_id}/image/{image_id}"
        params = {"private_key": rc._api_key}
        r = await rc._client.get(url, params=params)
        if r.status_code != 200:
            logger.warning(f"[routal-image-proxy] {report_id}/{image_id} → HTTP {r.status_code}")
            return None
        content_type = r.headers.get("content-type", "image/jpeg")
        return r.content, content_type
    except Exception as e:
        logger.error(f"[routal-image-proxy] error {report_id}/{image_id}: {e}")
        return None
    finally:
        try:
            await rc.aclose()
        except Exception:
            pass
