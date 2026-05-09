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
exposing the Routal API key in the browser. Image bytes are cached on disk
(`/tmp/routal_image_cache/`) with 7-day TTL — Routal images are immutable per
(report_id, image_id) so the cache is safe.
"""
import os
import logging
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────── Image cache (P0 perf fix) ───────────────
_CACHE_DIR = Path(os.environ.get("ROUTAL_IMAGE_CACHE_DIR", "/tmp/routal_image_cache"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL_SECS = int(os.environ.get("ROUTAL_IMAGE_CACHE_TTL_SECS", str(7 * 24 * 3600)))
_CACHE_LOCKS: dict = {}  # serialize concurrent fetches per key


def _cache_key(client_id: str, report_id: str, image_id: str) -> str:
    h = hashlib.sha1(f"{client_id}/{report_id}/{image_id}".encode()).hexdigest()
    return h


def _cache_paths(key: str) -> tuple:
    return _CACHE_DIR / f"{key}.bin", _CACHE_DIR / f"{key}.ctype"


def _read_cache(key: str) -> Optional[tuple]:
    bin_path, ctype_path = _cache_paths(key)
    if not bin_path.exists():
        return None
    age = datetime.now().timestamp() - bin_path.stat().st_mtime
    if age > _CACHE_TTL_SECS:
        try:
            bin_path.unlink()
            ctype_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    try:
        ctype = ctype_path.read_text() if ctype_path.exists() else "image/jpeg"
        return bin_path.read_bytes(), ctype
    except OSError as e:
        logger.warning(f"[routal-cache] read error: {e}")
        return None


def _write_cache(key: str, content: bytes, ctype: str) -> None:
    bin_path, ctype_path = _cache_paths(key)
    try:
        tmp = bin_path.with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.replace(bin_path)
        ctype_path.write_text(ctype)
    except OSError as e:
        logger.warning(f"[routal-cache] write error: {e}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_proxy_image_url(api_base: str, client_id: str, report_id: str, image_id: str) -> str:
    """Internal URL the browser will hit. Backend proxies the bytes from Routal
    using the stored client API key (never exposed to the frontend).
    """
    return f"{api_base.rstrip('/')}/api/integrations/routal/image/{client_id}/{report_id}/{image_id}"


async def _heal_outdated_plan_id(rc, journey: dict) -> Optional[str]:
    """Look up the current Routal plan_id for a journey when the stored one is stale.

    Strategy:
      1. List Routal plans for `journey.date` (paginated).
      2. Match by (a) routal_route_id present in plan.routes/drivers, OR
         (b) routal_driver_id, OR (c) plan.label matches journey.routal_plan_label,
         OR (d) driver_name matches one of the route labels.
      3. Return the plan_id of the first match, or None.
    """
    target_date = journey.get("date")  # YYYY-MM-DD
    if not target_date:
        return None
    try:
        from datetime import datetime, timedelta, timezone
        target_dt = datetime.fromisoformat(target_date).replace(tzinfo=timezone.utc)
        next_day = target_dt + timedelta(days=1)
    except Exception:
        return None

    route_id = journey.get("routal_route_id")
    driver_id = journey.get("routal_driver_id")
    plan_label = (journey.get("routal_plan_label") or "").strip().lower()
    driver_name = (journey.get("driver_name") or "").strip().lower()

    PAGE = 100
    for page in range(20):  # cap 2000 plans
        try:
            data = await rc._request("GET", "/v2/plans", params={"limit": PAGE, "offset": page * PAGE})
        except Exception as e:
            logger.warning(f"[routal-sync] heal-plan list_plans page={page} failed: {e}")
            return None
        plans = data if isinstance(data, list) else (data.get("docs") or data.get("data") or data.get("plans") or [])
        if not plans:
            return None
        page_below = 0
        for p in plans:
            exd = p.get("execution_date")
            if not exd:
                continue
            try:
                pdt = datetime.fromisoformat(str(exd).replace("Z", "+00:00"))
            except Exception:
                continue
            if pdt < target_dt:
                page_below += 1
                continue
            if pdt >= next_day:
                continue

            # In-range candidate. Match by route_id / driver_id / label / driver_name
            plan_id_candidate = p.get("id") or p.get("plan_id")
            if not plan_id_candidate:
                continue

            # Check route_id / driver_id by hydrating the plan once
            try:
                detail = await rc.get_plan(plan_id_candidate)
            except Exception:
                continue
            routes = detail.get("routes") or detail.get("drivers") or []

            if route_id and any(r.get("id") == route_id or r.get("external_id") == route_id for r in routes):
                return plan_id_candidate
            if driver_id and any((r.get("driver") or {}).get("id") == driver_id for r in routes):
                return plan_id_candidate
            if plan_label and (str(detail.get("label") or "")).strip().lower() == plan_label:
                return plan_id_candidate
            if driver_name and any(driver_name in str(r.get("label") or "").lower() for r in routes):
                return plan_id_candidate

        # Routal returns plans newest-first. Bail when whole pages are below target.
        if page_below >= len(plans) * 0.9:
            return None
        if len(plans) < PAGE:
            return None
    return None


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
        {"_id": 0, "id": 1, "client_id": 1, "routal_plan_id": 1, "routal_route_id": 1,
         "routal_driver_id": 1, "routal_plan_label": 1, "source": 1, "status": 1,
         "date": 1, "driver_name": 1},
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
            err = str(e)
            # Self-healing: Routal rotates plan_id when a plan is reorganized.
            # If the stored plan_id no longer exists, look up the current one
            # by execution_date + driver_name (or routal_route_id) and retry.
            if ("not_found" in err.lower() or "404" in err or "400" in err) and journey.get("date"):
                logger.info(f"[routal-sync] {journey_id} plan_id {plan_id} stale → self-heal lookup")
                healed_plan_id = await _heal_outdated_plan_id(rc, journey)
                if healed_plan_id and healed_plan_id != plan_id:
                    try:
                        detail = await rc.get_plan(healed_plan_id)
                        await db.journeys.update_one(
                            {"id": journey_id, "client_id": client_id},
                            {"$set": {
                                "routal_plan_id": healed_plan_id,
                                "routal_plan_id_healed_at": _now_iso(),
                            }, "$unset": {"routal_last_sync_error": ""}},
                        )
                        plan_id = healed_plan_id
                        logger.info(f"[routal-sync] {journey_id} healed plan_id {plan_id}")
                    except Exception as e2:
                        logger.error(f"[routal-sync] heal succeeded lookup but get_plan({healed_plan_id}) failed: {e2}")
                        return {"ok": False, "error": f"routal api error: {str(e2)[:200]}"}
                else:
                    logger.error(f"[routal-sync] get_plan {plan_id} failed and could not heal: {err}")
                    return {"ok": False, "error": f"routal api error: {err[:200]}"}
            else:
                logger.error(f"[routal-sync] get_plan {plan_id} failed: {err}")
                return {"ok": False, "error": f"routal api error: {err[:200]}"}

        stops_by_id = {s["id"]: s for s in (detail.get("stops") or []) if s.get("id")}

        # Index packages by routal_service_id (was set at journey creation time)
        packages = await db.packages.find(
            {"journey_id": journey_id, "client_id": client_id},
            {"_id": 0, "id": 1, "routal_service_id": 1, "status": 1, "kosmo_proof_count": 1,
             "recipient_name": 1, "address": 1, "tracking_number": 1, "order_reference_id": 1},
        ).to_list(length=10000)

        # If journey doesn't have routal_plan_label/project_id yet, persist them
        plan_label = detail.get("label")
        project_id_from_detail = detail.get("project_id") or detail.get("organization_id")
        meta_set = {}
        if plan_label:
            meta_set["routal_plan_label"] = plan_label
        if project_id_from_detail:
            meta_set["routal_project_id"] = project_id_from_detail
        if meta_set:
            await db.journeys.update_one({"id": journey_id, "client_id": client_id}, {"$set": meta_set})

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
                    and pkg.get("routal_report_id") == evidence.get("report_id")
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
    """Fetches a Routal report image bytes using the client's API key.
    Returns (content_bytes, content_type) or None if unavailable.

    Uses on-disk cache: first hit fetches from Routal (~1s for 1.4MB), subsequent
    hits read from /tmp in <5ms. Routal images are immutable per (report_id,
    image_id) so 7-day TTL is safe. Concurrent requests for the same key are
    coalesced via per-key asyncio.Lock to avoid duplicate Routal fetches.

    Self-healing: if Routal returns 400/404 (the report_id was rotated by Routal
    when the driver re-uploaded evidence), we look up the package by stored
    routal_report_id, query the latest plan from Routal, find the up-to-date
    report_id and image_ids, persist them, and retry once. This avoids the user
    having to manually click "Re-sincronizar" every time Routal rotates IDs.
    """
    key = _cache_key(client_id, report_id, image_id)
    cached = _read_cache(key)
    if cached:
        return cached

    # Coalesce concurrent fetches for the same key
    lock = _CACHE_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        # Re-check after acquiring lock (someone else may have populated)
        cached = _read_cache(key)
        if cached:
            return cached

        from services.integration_service import IntegrationService
        svc = IntegrationService(db)
        rc = await svc.get_routal_client(client_id)
        if not rc:
            return None
        try:
            url = f"{rc._base_url}/v3/stop/report/{report_id}/image/{image_id}"
            params = {"private_key": rc._api_key}
            r = await rc._client.get(url, params=params)
            if r.status_code == 200:
                content_type = r.headers.get("content-type", "image/jpeg")
                _write_cache(key, r.content, content_type)
                return r.content, content_type

            # SELF-HEALING — Routal rotated this report_id (driver re-uploaded
            # evidence). Try to resolve the new report_id and retry once.
            if r.status_code in (400, 404):
                logger.info(
                    f"[routal-image-proxy] {report_id}/{image_id} → HTTP {r.status_code}, "
                    f"attempting self-heal"
                )
                healed = await _heal_outdated_report_id(db, rc, client_id, report_id, image_id)
                if healed:
                    new_report_id, new_image_id = healed
                    new_url = f"{rc._base_url}/v3/stop/report/{new_report_id}/image/{new_image_id}"
                    r2 = await rc._client.get(new_url, params=params)
                    if r2.status_code == 200:
                        content_type = r2.headers.get("content-type", "image/jpeg")
                        # Cache under BOTH old and new keys so subsequent hits
                        # to the cached old URL also succeed instantly.
                        _write_cache(key, r2.content, content_type)
                        _write_cache(_cache_key(client_id, new_report_id, new_image_id), r2.content, content_type)
                        logger.info(
                            f"[routal-image-proxy] healed {report_id}/{image_id} → "
                            f"{new_report_id}/{new_image_id}"
                        )
                        return r2.content, content_type

            logger.warning(f"[routal-image-proxy] {report_id}/{image_id} → HTTP {r.status_code}")
            return None
        except Exception as e:
            logger.error(f"[routal-image-proxy] error {report_id}/{image_id}: {e}")
            return None
        finally:
            try:
                await rc.aclose()
            except Exception:
                pass


async def _heal_outdated_report_id(db, rc, client_id: str, report_id: str, image_id: str) -> Optional[tuple]:
    """Refresh URLs of packages that reference a stale report_id.

    Strategy:
    1. Find any LastMile package using this (client_id, report_id, image_id).
    2. Look up the plan via journey.routal_plan_id.
    3. Pull plan.stops from Routal API. For each completed stop with reports,
       map the report position (1st report → 1st stop with reports, etc.) is
       NOT reliable — instead match by tracking_number / external_id since the
       package already has this. Updated report and its images replace
       kosmo_proof_urls + routal_report_id.
    4. Bulk-update all packages of this stop to the new IDs.
    5. Return (new_report_id, new_image_id_at_same_index) so the caller can
       retry the SAME image position.
    """
    try:
        pkg = await db.packages.find_one(
            {"routal_report_id": report_id},
            {"_id": 0, "id": 1, "journey_id": 1, "tracking_number": 1,
             "kosmo_proof_urls": 1, "kosmo_proof_signature_url": 1, "kosmo_proof_count": 1},
        )
        if not pkg:
            return None
        old_urls = pkg.get("kosmo_proof_urls") or []
        # Index of the requested image inside the old URL list (so we can return
        # the correct corresponding new image_id).
        try:
            old_idx = next(i for i, u in enumerate(old_urls) if image_id in str(u))
        except StopIteration:
            return None

        journey = await db.journeys.find_one(
            {"id": pkg["journey_id"]},
            {"_id": 0, "routal_plan_id": 1, "client_id": 1},
        )
        if not journey or not journey.get("routal_plan_id"):
            return None

        plan = await rc.get_plan(journey["routal_plan_id"])
        stops = plan.get("stops") or []
        # Match the stop by tracking_number / external_id / reference_id
        tn = pkg.get("tracking_number")
        target_stop = None
        for s in stops:
            external = " ".join(str(s.get(k) or "") for k in ("external_id", "reference_id", "label", "id"))
            if tn and tn in external:
                target_stop = s
                break
        if not target_stop:
            return None

        reports = target_stop.get("reports") or []
        # Pick the most recent completed report
        completed = [r for r in reports if r.get("type") in ("service_report_completed", "service_report_failed", "service_report_incomplete")]
        if not completed:
            return None
        report = completed[-1]
        new_report_id = report.get("id")
        new_images = report.get("images") or []
        if not new_report_id or old_idx >= len(new_images):
            return None
        new_image_id = new_images[old_idx].get("id")
        if not new_image_id:
            return None

        # Persist the refreshed URLs for ALL images of this report (not just one)
        api_base = os.environ.get("REACT_APP_BACKEND_URL", "")
        new_urls = [
            f"{api_base}/api/integrations/routal/image/{client_id}/{new_report_id}/{img['id']}"
            for img in new_images if img.get("id")
        ]
        await db.packages.update_one(
            {"id": pkg["id"]},
            {"$set": {
                "kosmo_proof_urls": new_urls,
                "kosmo_proof_count": len(new_urls),
                "routal_report_id": new_report_id,
                "routal_report_id_healed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return new_report_id, new_image_id
    except Exception as e:
        logger.warning(f"[routal-image-proxy] heal failed for {report_id}: {e}")
        return None

