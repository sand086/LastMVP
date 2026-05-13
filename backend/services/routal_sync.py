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

        # Fallback index: para sanar packages cuyo routal_service_id quedó stale
        # (Routal puede rotar stop.id, o el package se creó con un id histórico).
        # Indexamos los stops por TODAS sus claves alternativas para poder
        # re-matchear por tracking_number / reference / external_id / fixed_id.
        # Una misma stop puede aparecer bajo varias claves — la última gana, lo
        # cual es seguro porque apuntamos al mismo objeto stop.
        stops_by_altkey = {}
        for s in (detail.get("stops") or []):
            for alt_key in (
                s.get("tracking_number"),
                s.get("reference"),
                s.get("client_external_id"),
                s.get("fixed_id"),
            ):
                if alt_key:
                    stops_by_altkey[str(alt_key)] = s

        # Index packages by routal_service_id (was set at journey creation time)
        packages = await db.packages.find(
            {"journey_id": journey_id, "client_id": client_id},
            {"_id": 0, "id": 1, "routal_service_id": 1, "status": 1, "kosmo_proof_count": 1,
             "recipient_name": 1, "address": 1, "tracking_number": 1, "order_reference_id": 1,
             "routal_report_id": 1},
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
        recovered_by_fallback = 0  # packages cuyo routal_service_id se sanó por tracking_number

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
            stop = stops_by_id.get(svc_id) if svc_id else None

            # Fallback matching: si el routal_service_id no matchea (porque
            # Routal rotó stop.id, o el id histórico ya no existe), intentamos
            # re-matchear por tracking_number contra las claves alternativas
            # del stop (tracking_number, reference, client_external_id, fixed_id).
            # Si encontramos match por fallback, persistimos el nuevo
            # routal_service_id en el package — próximas syncs ya matchean
            # directo sin volver a hacer este lookup.
            if stop is None:
                pkg_tracking = pkg.get("tracking_number") or pkg.get("order_reference_id")
                if pkg_tracking and str(pkg_tracking) in stops_by_altkey:
                    stop = stops_by_altkey[str(pkg_tracking)]
                    new_svc_id = stop.get("id")
                    if new_svc_id and new_svc_id != svc_id:
                        await db.packages.update_one(
                            {"id": pkg["id"], "client_id": client_id},
                            {"$set": {
                                "routal_service_id": new_svc_id,
                                "routal_service_id_healed_at": _now_iso(),
                            }},
                        )
                        # Reflejar el cambio en el dict en memoria para que
                        # _build_recipient_update y demás logica use el id nuevo.
                        pkg["routal_service_id"] = new_svc_id
                        recovered_by_fallback += 1
                        logger.info(
                            f"[routal-sync] healed routal_service_id for pkg={pkg['id'][:8]} "
                            f"by tracking_number={pkg_tracking}: {svc_id} → {new_svc_id}"
                        )

            if stop is None:
                no_match += 1
                continue
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
                if pkg.get("status") == "failed" and not ru and pkg.get("kosmo_driver_note"):
                    # Solo skip si ya tenía la nota — antes saltábamos sin importar
                    # si la nota estaba persistida, lo que dejó 433 packages sin
                    # ella tras la migración Routal-only.
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
                    # Persistir nota del driver para que la UI la muestre
                    # ("Comentarios" en Routal). Antes solo se hacía en la
                    # rama de delivered, dejando 99.8% de las failed vacías.
                    if evidence.get("driver_note"):
                        update["kosmo_driver_note"] = evidence["driver_note"]
                    if evidence.get("signature_url"):
                        update["routal_signature_url"] = evidence["signature_url"]
                    if evidence.get("report_id"):
                        update["routal_report_id"] = evidence["report_id"]
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
            "recovered_by_fallback": recovered_by_fallback,
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

    NOTE: This proxy does NOT auto-heal stale report_ids. If Routal rotates the
    report_id (e.g. driver re-uploaded evidence hours after closure), the user
    must explicitly press the "Re-sincronizar Routal" button to refresh the
    package URLs. Background self-healing was removed intentionally to avoid
    repeated heavy lookups on every image render and to enforce manual control
    over operational malpractice.
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

