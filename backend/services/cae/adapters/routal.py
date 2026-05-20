"""Routal carrier adapter — REAL HTTP integration (PROMPT 20 + multi-project).

Routal is a route-optimization platform. Each `stop` is a delivery attempt.
Auth is `private_key` query string (not a header).

Multi-project model:
  * One Routal API key can manage N projects (1:N for ingestion).
  * Each stop lives inside a specific project; updates must target that
    SAME project (1:1 for outbound `send_instruction`).
  * The adapter therefore accepts a list of `project_ids` at construction
    time, plus an optional explicit `project_id` per call.

Mapping:
  Routal status  → MyExcellence canonical
  -------------- → -----------------------
  pending        → in_transit  (no terminal)
  incomplete     → exception   (acción requerida)
  completed      → delivered   (terminal)
  canceled       → cancelled   (terminal)
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from core.errors import MyEException, ErrorCode
from core.logger import log
from ..interface import ApiResponse, CarrierAdapterInterface, RawCarrierEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RoutalAdapter(CarrierAdapterInterface):
    """Real HTTP adapter for Routal.

    Construction options:
      * ``RoutalAdapter()`` — falls back to env (legacy single-tenant mode,
        kept for transversal health probes at /admin/carriers/{code}/health).
      * ``RoutalAdapter(api_key=..., project_ids=["p1","p2"])`` — for SaaS
        per-client usage. The scheduler builds adapters this way.
    """
    carrier_id = "routal"
    DEFAULT_API_VERSION: ClassVar[str] = "v2"

    #: raw_code → (canonical, incident_type, is_terminal, requires_action,
    #: display_label_es, confidence)
    NATIVE_CODES: ClassVar[dict[str, tuple]] = {
        "pending":    ("in_transit",  None,             False, False, "Pendiente / en camino",      95),
        "incomplete": ("exception",   "failed",         False, True,  "Entrega incompleta",          92),
        "completed":  ("delivered",   None,             True,  False, "Entregado",                  100),
        "canceled":   ("cancelled",   None,             True,  False, "Cancelado",                  100),
    }

    def __init__(self, *,
                 api_key: str | None = None,
                 project_ids: list[str] | None = None,
                 base_url: str | None = None,
                 timeout: float | None = None) -> None:
        # env fallbacks make `RoutalAdapter()` continue to work for the
        # tenant-level admin health endpoint (transversal); per-client
        # callers pass explicit args.
        self.api_key: str = api_key or os.environ.get("ROUTAL_API_KEY", "")
        if project_ids is None:
            env_pid = os.environ.get("ROUTAL_PROJECT_ID", "")
            self.project_ids: list[str] = [env_pid] if env_pid else []
        else:
            self.project_ids = [p for p in project_ids if p]
        self.base_url: str = base_url or os.environ.get(
            "ROUTAL_BASE_URL", "https://api.routal.com")
        self.timeout: float = float(timeout if timeout is not None
                                    else os.environ.get("ROUTAL_TIMEOUT", "10"))

    # ─── public ─────────────────────────────────────────────────────────
    @property
    def default_project_id(self) -> str | None:
        return self.project_ids[0] if self.project_ids else None

    async def validate_config(self) -> bool:
        """Cheap sanity-check: list 1 plan from the FIRST configured project."""
        if not self.api_key or not self.project_ids:
            return False
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as ac:
                r = await ac.get(f"{self.base_url}/v2/plans", params={
                    "private_key": self.api_key,
                    "project_id": self.default_project_id,
                    "limit": 1,
                })
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def get_raw_status(self, tracking_id: str, *,
                             project_id: str | None = None) -> RawCarrierEvent:
        """Find a stop by ``external_id == tracking_id`` and return the raw event.

        If ``project_id`` is passed (the usual case for updates on an existing
        guía), the lookup is restricted to that project. Otherwise the adapter
        searches each configured project in order until it finds a match.
        """
        stop = await self._find_stop(tracking_id, project_id=project_id)
        if not stop:
            return RawCarrierEvent(
                carrier_id=self.carrier_id,
                tracking_id=tracking_id,
                raw_code="unknown",
                raw_description="Stop no encontrado en Routal",
                raw_payload={"tracking_id": tracking_id, "found": False},
                api_version=self.DEFAULT_API_VERSION,
                event_at=_now(),
            )
        return self._stop_to_event(tracking_id, stop)

    async def send_instruction(self, tracking_id: str, payload: dict) -> ApiResponse:
        """Update the matching stop's status (e.g. cancel from MyExcellence).

        ``payload`` accepts:
          * ``status``  — required, one of pending/incomplete/completed/canceled
          * ``project_id`` — strongly recommended; if omitted the adapter
            falls back to the first configured project. For Cubbo (multi-project)
            the caller MUST pass the project_id stored on the guía.
          * ``comments`` — optional free-text note attached on Routal side.
        """
        target_status = (payload or {}).get("status")
        if target_status not in {"pending", "incomplete", "completed", "canceled"}:
            return ApiResponse(received=False, status=400)
        project_id = (payload or {}).get("project_id") or self.default_project_id
        if not project_id:
            return ApiResponse(received=False, status=400, fallback_to_email=True)
        stop = await self._find_stop(tracking_id, project_id=project_id)
        if not stop:
            return ApiResponse(received=False, status=404, fallback_to_email=True)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as ac:
                r = await ac.put(
                    f"{self.base_url}/v2/stop/{stop['id']}",
                    params={"private_key": self.api_key},
                    json={"status": target_status,
                          "comments": (payload or {}).get("comments")},
                )
            return ApiResponse(received=r.status_code == 200, status=r.status_code,
                               fallback_to_email=r.status_code != 200)
        except httpx.HTTPError as e:
            log.warning("routal_send_instruction_failed",
                        extra={"context": {"tracking_id": tracking_id,
                                           "project_id": project_id, "error": str(e)}})
            return ApiResponse(received=False, status=502, fallback_to_email=True)

    async def list_recent_plans(self, *, project_id: str | None = None,
                                 limit: int = 10,
                                 created_from: str | None = None,
                                 created_to: str | None = None) -> list[dict]:
        """Iter56 — soporta filtrado por rango `created_at` (filtrado local).

        Routal devuelve `created_at` ISO 8601 (UTC). Si se proveen
        `created_from`/`created_to` (ISO strings), filtramos localmente. Si
        no, devuelve los `limit` más recientes.
        """
        pid = project_id or self.default_project_id
        self._require_creds(pid)
        # Cuando hay rango, paginamos para garantizar cobertura completa.
        page_size = max(limit, 100) if (created_from or created_to) else limit
        async with httpx.AsyncClient(timeout=self.timeout) as ac:
            r = await ac.get(
                f"{self.base_url}/v2/plans",
                params={"private_key": self.api_key, "project_id": pid,
                        "limit": page_size, "sort": "created_at:desc"},
            )
        if r.status_code != 200:
            return []
        data = r.json()
        plans = data.get("docs") or [] if isinstance(data, dict) else (data or [])
        if not (created_from or created_to):
            return plans
        # Filtrar local
        out = []
        for p in plans:
            ca = p.get("created_at") or p.get("start_at") or ""
            if not ca:
                continue
            if created_from and ca < created_from:
                continue
            if created_to and ca > created_to:
                continue
            out.append(p)
        return out

    async def list_stops_in_plan(self, plan_id: str) -> list[dict]:
        """Plans are project-scoped on Routal's side; the API key alone is
        enough to fetch their stops once you have a plan_id."""
        if not self.api_key:
            self._require_creds(None)
        async with httpx.AsyncClient(timeout=self.timeout) as ac:
            r = await ac.get(
                f"{self.base_url}/v2/plan/{plan_id}/stops",
                params={"private_key": self.api_key},
            )
        if r.status_code != 200:
            return []
        data = r.json()
        return data if isinstance(data, list) else (data.get("docs") or [])

    # ─── helpers ───────────────────────────────────────────────────────
    def _require_creds(self, project_id: str | None) -> None:
        if not self.api_key:
            raise MyEException(ErrorCode.VALIDATION_FAILED,
                               "Routal API key no configurado para este cliente")
        if project_id is None and not self.project_ids:
            raise MyEException(ErrorCode.VALIDATION_FAILED,
                               "Routal sin project_id configurado")

    async def _find_stop(self, tracking_id: str, *,
                         project_id: str | None) -> dict | None:
        """Search the stop in a specific project; if none provided, iterate
        all configured projects (preserves the 1:N ingest model)."""
        projects = [project_id] if project_id else list(self.project_ids)
        for pid in projects:
            stop = await self._search_stop_by_external_id(tracking_id, project_id=pid)
            if stop:
                # tag the found project so callers can persist it on the guía
                stop["_routal_project_id"] = pid
                return stop
        return None

    async def _search_stop_by_external_id(self, tracking_id: str, *,
                                           project_id: str) -> dict | None:
        self._require_creds(project_id)
        body = {
            "limit": 1, "offset": 0, "sort_by": "created_at",
            "sort_direction": "desc",
            "predicates": [
                {"field": "external_id", "operator": "eq",
                 "value": tracking_id, "type": "string"},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as ac:
                r = await ac.post(
                    f"{self.base_url}/v2/stops/search",
                    params={"private_key": self.api_key, "project_id": project_id},
                    json=body,
                )
        except httpx.HTTPError as e:
            log.warning("routal_search_failed",
                        extra={"context": {"tracking_id": tracking_id,
                                           "project_id": project_id, "error": str(e)}})
            return None
        if r.status_code != 200:
            log.warning("routal_search_non_200", extra={"context": {
                "tracking_id": tracking_id, "project_id": project_id,
                "status": r.status_code, "body": r.text[:200],
            }})
            return None
        data = r.json()
        if isinstance(data, list):
            return data[0] if data else None
        docs = data.get("docs") or data.get("items") or []
        return docs[0] if docs else None

    def _stop_to_event(self, tracking_id: str, stop: dict) -> RawCarrierEvent:
        raw = (stop.get("status") or "pending").lower()
        meta = self.NATIVE_CODES.get(raw)
        description = meta[4] if meta else raw
        loc = stop.get("location") or {}
        event_at_iso = stop.get("updated_at") or stop.get("created_at")
        try:
            event_at = (datetime.fromisoformat(event_at_iso.replace("Z", "+00:00"))
                        if event_at_iso else _now())
        except Exception:  # noqa: BLE001
            event_at = _now()
        # Iter61 — Extraer el primer report (driver feedback) cuando exista.
        # Routal lo trae para stops finalizadas (completed/canceled/incomplete).
        # El report contiene:
        #   - type: "service_report_canceled" / "_completed" / "_incomplete"
        #   - comments: texto libre del driver (motivo en lenguaje natural)
        #   - custom_fields.motivos_de_cancelacion.label: motivo categorizado
        #   - images[]: fotos adjuntas (URLs)
        #   - location: {lat,lng} donde el driver registró el report
        report_payload = _extract_first_report(stop)
        return RawCarrierEvent(
            carrier_id=self.carrier_id,
            tracking_id=tracking_id,
            raw_code=raw,
            raw_description=description,
            raw_payload={
                "stop_id": stop.get("id"),
                "plan_id": stop.get("plan_id"),
                "label": stop.get("label"),
                "external_id": stop.get("external_id"),
                # CRITICAL for the 1:1 send_instruction back-channel:
                "routal_project_id": stop.get("_routal_project_id") or stop.get("project_id"),
                "location": {
                    "lat": loc.get("lat"), "lng": loc.get("lng"),
                    "address": loc.get("main_text") or loc.get("label"),
                    "full_address": loc.get("label"),
                    "street": loc.get("street"),
                    "house_number": loc.get("house_number"),
                    "city": loc.get("city"),
                    "state": loc.get("state"),
                    "postal_code": loc.get("postal_code"),
                    "country": loc.get("country") or loc.get("country_code"),
                    "country_code": loc.get("country_code"),
                },
                "phone": stop.get("phone"),
                "email": stop.get("email"),
                "estimated_arrival_time": stop.get("estimated_arrival_time"),
                "reports_count": len(stop.get("reports") or []),
                **({"routal_report": report_payload} if report_payload else {}),
            },
            api_version=self.DEFAULT_API_VERSION,
            event_at=event_at,
        )


def _extract_first_report(stop: dict) -> dict | None:
    """Iter61 — Normaliza el primer report (driver feedback) de un stop Routal.

    Devuelve un dict con los campos relevantes para tickets de incidencia o
    None si el stop no tiene reports.
    """
    reports = stop.get("reports") or []
    if not reports:
        return None
    r = reports[0]
    custom = r.get("custom_fields") or {}
    # `motivos_de_cancelacion` es el caso real de Cubbo; otros clientes
    # podrían tener otros nombres de custom_field — los exponemos completos.
    reason_label = None
    cancel_field = custom.get("motivos_de_cancelacion")
    if isinstance(cancel_field, dict):
        reason_label = cancel_field.get("label")
    images = r.get("images") or []
    return {
        "report_id": r.get("id"),
        "report_type": r.get("type"),  # service_report_canceled, _completed, _incomplete
        "comments": (r.get("comments") or "").strip() or None,
        "reason_label": reason_label,
        "custom_fields": custom,
        "images": [{"id": im.get("id"), "url": im.get("url")} for im in images],
        "images_count": len(images),
        "location": r.get("location") or {},
        "report_at": r.get("created_at"),
        "driver_id": r.get("driver_id"),
    }
