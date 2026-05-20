"""Real IngestService — replaces the stub from PROMPT_01 P0.14.

Handles the three ingest modes (webhook, pulling, layout) at the *transport*
level. The decision tree (whether to escalate the guía to a ticket, run
automation, etc.) lives in the WorkflowEngine and is wired in PROMPT_05.

Rules enforced here:
  R01 — every write goes through tenant-scoped repositories
  R02 — guías with is_terminal=True silently ignore updates
  R10 — every response uses the standard envelope (handled by routers)
"""
from __future__ import annotations
import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone

from core.errors import ResourceNotFoundException
from core.logger import log
from repositories.guias import GuiaRepository
from repositories.clients import ClientRepository
from repositories.carriers import CarrierRepository
from services.cae.interface import RawCarrierEvent
from services.cae.normalizer import StatusNormalizer
from services.workflow_engine import WorkflowEngine

# Carrier statuses considered terminal at ingest level — until the proper
# Carrier Adapter Engine catalog (PROMPT_06) lands. Conservative list to
# avoid premature freezing.
_TERMINAL_HINTS_DELIVERED = {"DELIVERED", "ENTREGADO", "DL",
                              "DELIVERY_COMPLETED", "COMPLETED"}
_TERMINAL_HINTS_RETURNED  = {"RETURNED", "DEVUELTO", "DEVOLUCIÓN", "DEVOLUCION",
                              "RT", "RETURN_COMPLETED",
                              "CANCELED", "CANCELLED", "CANCELADO"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _internal_status_from_carrier(carrier_status: str) -> tuple[str, bool]:
    """Tiny pre-CAE heuristic: maps an obvious terminal hint to the right state.

    Returns (internal_status, is_terminal). Anything we don't recognise stays
    as ``in_transit``. PROMPT_06 replaces this with the catalog lookup.
    """
    cs = (carrier_status or "").strip().upper()
    if cs in _TERMINAL_HINTS_DELIVERED:
        return "delivered", True
    if cs in _TERMINAL_HINTS_RETURNED:
        return "returned", True
    return "in_transit", False


def _synthesize_recipient_from_raw_payload(rp: dict) -> dict | None:
    """Iter62 — Construye un ``recipient`` legible para la UI del agente a
    partir del raw_payload de un adapter pull (típicamente Routal).

    Se invoca sólo cuando el caller no pasó ``recipient`` explícito (ej.
    webhooks o layouts ya lo traen estructurado). Devuelve None si no hay
    suficiente data en el raw_payload.
    """
    loc = rp.get("location") or {}
    label = rp.get("label") or ""
    # `label` típico de Routal: "Nombre del cliente - tracking_id"
    # Extraemos el nombre quitando el sufijo del tracking si existe.
    name = None
    if label:
        # quitar "- TRK123" del final si parece tracking_id
        parts = label.rsplit(" - ", 1)
        if len(parts) == 2 and len(parts[1]) <= 30 and " " not in parts[1]:
            name = parts[0].strip()
        else:
            name = label.strip()
    address = (loc.get("full_address")
               or loc.get("address")
               or loc.get("label"))
    out = {k: v for k, v in {
        "name": name,
        "address": address,
        "city": loc.get("city"),
        "state": loc.get("state"),
        "cp": loc.get("postal_code"),
        "country": loc.get("country") or loc.get("country_code"),
        "phone": rp.get("phone"),
        "email": rp.get("email"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
    }.items() if v is not None and v != ""}
    return out or None


@dataclass
class IngestOutcome:
    action: str  # 'created' | 'updated' | 'discarded_terminal' | 'discarded_no_change'
    guia_id: str | None
    tracking_id: str
    is_terminal: bool
    canonical_status: str | None = None
    incident_type: str | None = None
    workflow_action: str | None = None
    ticket_id: str | None = None


class IngestService:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.guias = GuiaRepository(tenant_id=tenant_id)
        self.clients = ClientRepository(tenant_id=tenant_id)
        self.carriers = CarrierRepository(tenant_id=tenant_id)

    # ---------- Webhook -------------------------------------------------
    async def process_event(
        self,
        *,
        client_id: str,
        tracking_id: str,
        carrier_code: str,
        carrier_status: str,
        carrier_status_description: str | None = None,
        raw_code: str | None = None,
        api_version: str = "v1",
        event_at: str | None = None,
        raw_payload: dict | None = None,
        source: str = "webhook",
        carrier_meta: dict | None = None,
        # Layout v2 — Iter39 — extended structured fields (optional)
        sender: dict | None = None,
        recipient: dict | None = None,
        service: dict | None = None,
        weights: dict | None = None,
        declared_value: float | None = None,
        insurance_purchased: bool | None = None,
        delivery_notes: str | None = None,
        carrier_incidence: str | None = None,
        external_tms_client_id: str | None = None,
        external_reference: str | None = None,
        delivered_at_external: str | None = None,
        shipped_at_external: str | None = None,
        created_at_external: str | None = None,
    ) -> IngestOutcome:
        client = await self.clients.find_one({"id": client_id})
        if not client:
            raise ResourceNotFoundException("Cliente no encontrado.")

        carrier = await self.carriers.find_one({"code": carrier_code.lower()})
        carrier_id = carrier["id"] if carrier else None  # allow ingest of unknown carriers

        # Iter61 — Si raw_payload trae un routal_report estructurado, copiarlo
        # a carrier_meta para acceso fácil desde la UI/Workflow, y rellenar
        # `carrier_incidence` si está vacío (motivo legible para el agente).
        rp = raw_payload or {}
        rr = rp.get("routal_report")
        if rr and isinstance(rr, dict):
            carrier_meta = dict(carrier_meta or {})
            carrier_meta.setdefault("routal_report", rr)
            if not carrier_incidence:
                carrier_incidence = (rr.get("reason_label")
                                     or rr.get("comments")
                                     or carrier_incidence)

        # Iter62 — Sintetizar `recipient` desde raw_payload cuando el cliente
        # ingesta vía pull/webhook sin Layout V2 (caso Routal). El driver del
        # carrier ya conoce el destinatario (label/phone/email/location), así
        # que enriquecemos para que el agente vea contacto + dirección + map
        # link sin depender de un Layout CSV separado.
        if recipient is None and rp:
            synthesized = _synthesize_recipient_from_raw_payload(rp)
            if synthesized:
                recipient = synthesized

        # Find existing guía
        existing = await self.guias.find_one({
            "client_id": client_id,
            "tracking_id": tracking_id,
        })

        # Iter60 — Catálogo CAE manda sobre la heurística pre-CAE.
        # Antes: `_internal_status_from_carrier(carrier_status)` mapeaba
        # CANCELED→returned hardcoded, pisando el catálogo. Ahora consultamos
        # el normalizer primero (si hay raw_code) y sólo caemos a la heurística
        # cuando el catálogo no tiene el código.
        new_internal, terminal_flip, normalized_incident_pre = (
            await self._resolve_internal_status(
                carrier_code=carrier_code, raw_code=raw_code,
                api_version=api_version, carrier_status=carrier_status,
                raw_description=carrier_status_description,
                raw_payload=raw_payload or {},
            )
        )

        # R02 — terminal state never overwritten
        if existing and existing.get("is_terminal"):
            log.info("ingest_skipped_terminal", extra={"context": {
                "tenant_id": self.tenant_id, "tracking_id": tracking_id,
                "guia_id": existing["id"],
            }})
            return IngestOutcome("discarded_terminal", existing["id"], tracking_id, True)

        if not existing:
            # Layout v2 extended fields — drop None values so the doc stays
            # clean. Bag is preserved verbatim if explicitly provided.
            extended = {k: v for k, v in {
                "sender": sender, "recipient": recipient, "service": service,
                "weights": weights, "declared_value": declared_value,
                "insurance_purchased": insurance_purchased,
                "delivery_notes": delivery_notes,
                "carrier_incidence": carrier_incidence,
                "external_tms_client_id": external_tms_client_id,
                "external_reference": external_reference,
                "delivered_at_external": delivered_at_external,
                "shipped_at_external": shipped_at_external,
                "created_at_external": created_at_external,
            }.items() if v is not None}
            doc = await self.guias.insert({
                "tracking_id": tracking_id,
                "client_id": client_id,
                "subclient_id": None,
                "carrier_id": carrier_id,
                "carrier_code": carrier_code.lower(),
                "carrier_status": carrier_status,
                "carrier_status_description": carrier_status_description,
                "raw_code": raw_code,
                "api_version": api_version,
                "internal_status": new_internal,
                "is_terminal": terminal_flip,
                "ingest_source": source,
                "last_ingest_at": _now_iso(),
                "raw_payload": raw_payload or {},
                "carrier_meta": carrier_meta or {},
                "event_at": event_at or _now_iso(),
                # Iter55 P3.2 — `delivery_attempts` desde adapter (FedEx etc.)
                "delivery_attempts": (raw_payload or {}).get("delivery_attempts") or 0,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                **extended,
            })
            log.info("ingest_created", extra={"context": {
                "tenant_id": self.tenant_id, "tracking_id": tracking_id,
                "guia_id": doc["id"], "carrier_status": carrier_status,
            }})
            outcome = IngestOutcome("created", doc["id"], tracking_id, terminal_flip)
            await self._dispatch_workflow(outcome, raw_code=raw_code, carrier_code=carrier_code,
                                          api_version=api_version, raw_payload=raw_payload or {})
            return outcome

        # Update path — same status? skip; otherwise update
        if existing.get("carrier_status") == carrier_status and not terminal_flip:
            await self.guias.update_one(
                {"id": existing["id"]},
                {"last_ingest_at": _now_iso(), "updated_at": _now_iso()},
            )
            return IngestOutcome("discarded_no_change", existing["id"], tracking_id, False)

        update_fields = {
            "carrier_status": carrier_status,
            "carrier_status_description": carrier_status_description,
            "raw_code": raw_code,
            "api_version": api_version,
            "internal_status": new_internal,
            "is_terminal": terminal_flip,
            "last_ingest_at": _now_iso(),
            "event_at": event_at or _now_iso(),
            "updated_at": _now_iso(),
        }
        # Iter55 P3.2 — propagar `delivery_attempts` desde raw_payload del
        # adapter del carrier (FedEx ya lo trae; otros lo agregarán a futuro).
        # También aceptamos override directo en kwargs (CSV layout v2 puede
        # incluir intentos explícitamente).
        rp_attempts = (raw_payload or {}).get("delivery_attempts")
        if isinstance(rp_attempts, int) and rp_attempts > 0:
            # max(existing, new) — los attempts son monotónicos
            existing_attempts = existing.get("delivery_attempts") or 0
            update_fields["delivery_attempts"] = max(existing_attempts, rp_attempts)
        if carrier_meta:
            # Merge non-empty meta keys preserving existing ones the caller
            # didn't touch (e.g. routal_project_id from the very first ingest).
            existing_meta = existing.get("carrier_meta") or {}
            update_fields["carrier_meta"] = {**existing_meta, **carrier_meta}
        # Layout v2 — sólo escribimos campos extendidos si vienen y aún NO
        # están en el doc (first-write-wins; el ingest layout puede llegar
        # antes o después del webhook, así que respetamos lo ya capturado).
        for key, val in {
            "sender": sender, "recipient": recipient, "service": service,
            "weights": weights, "declared_value": declared_value,
            "insurance_purchased": insurance_purchased,
            "delivery_notes": delivery_notes,
            "carrier_incidence": carrier_incidence,
            "external_tms_client_id": external_tms_client_id,
            "external_reference": external_reference,
            "delivered_at_external": delivered_at_external,
            "shipped_at_external": shipped_at_external,
            "created_at_external": created_at_external,
        }.items():
            if val is not None and not existing.get(key):
                update_fields[key] = val
        await self.guias.update_one({"id": existing["id"]}, update_fields)
        # Iter55 P3.2 — heurística: si el carrier_status indica "intento" y
        # el adapter no trajo `delivery_attempts` explícitos, incrementamos
        # nuestro contador interno (idempotente por (guia, status, event_at)).
        if not isinstance(rp_attempts, int):
            from services.delivery_attempts import bump_attempts_if_event_indicates
            await bump_attempts_if_event_indicates(
                tenant_id=self.tenant_id, guia_id=existing["id"],
                carrier_status=carrier_status, event_at=event_at,
            )
        log.info("ingest_updated", extra={"context": {
            "tenant_id": self.tenant_id, "tracking_id": tracking_id,
            "guia_id": existing["id"], "carrier_status": carrier_status,
            "is_terminal": terminal_flip,
        }})
        outcome = IngestOutcome("updated", existing["id"], tracking_id, terminal_flip)
        await self._dispatch_workflow(outcome, raw_code=raw_code, carrier_code=carrier_code,
                                      api_version=api_version, raw_payload=raw_payload or {})
        return outcome

    async def _resolve_internal_status(
        self, *, carrier_code: str, raw_code: str | None,
        api_version: str, carrier_status: str,
        raw_description: str | None, raw_payload: dict,
    ) -> tuple[str, bool, str | None]:
        """Iter60 — Mapea (carrier, raw_code) → (internal_status, is_terminal,
        incident_type) preferentemente vía catálogo CAE.

        Si el catálogo tiene un mapeo activo, lo usamos. Si no, caemos a la
        heurística pre-CAE ``_internal_status_from_carrier`` (compat con
        webhooks que aún no traen raw_code limpio).

        Returns:
          - new_internal: uno de {in_transit, delivered, returned, exception,
                                  cancelled, unknown}
          - is_terminal: bool
          - incident_type: opcional (sólo si el catálogo lo declara)
        """
        if raw_code:
            from datetime import datetime, timezone as _tz
            event = RawCarrierEvent(
                carrier_id=carrier_code.lower(),
                tracking_id="",
                raw_code=raw_code,
                raw_description=raw_description,
                raw_payload=raw_payload,
                api_version=api_version,
                event_at=datetime.now(_tz.utc),
            )
            normalized = await StatusNormalizer(
                tenant_id=self.tenant_id).normalize(event)
            if normalized.canonical_status != "unknown":
                canonical = normalized.canonical_status
                # Mapeo canonical → internal_status. Para los 6 canónicos del
                # catálogo CAE usamos el mismo nombre como internal_status
                # (delivered, returned, exception, cancelled, in_transit,
                # unknown). is_terminal viene del catálogo.
                return (canonical, bool(normalized.is_terminal),
                        normalized.incident_type)
        # Fallback heurística (pre-CAE) para casos sin raw_code o sin mapeo.
        ni, term = _internal_status_from_carrier(carrier_status)
        return (ni, term, None)

    async def _dispatch_workflow(
        self,
        outcome: IngestOutcome,
        *,
        raw_code: str | None,
        carrier_code: str,
        api_version: str,
        raw_payload: dict,
    ) -> None:
        """After a successful ingest, run the normalizer + WorkflowEngine.

        Chained tightly so that:
          * Adapter knowledge (raw_code semantics) lives in CAE
          * Engine receives ONLY normalized data (R21)
        """
        if outcome.action not in ("created", "updated") or not outcome.guia_id:
            return

        # Normalize when we have a raw_code; otherwise just pass canonical=None
        normalized_canonical = None
        normalized_incident = None
        if raw_code:
            from datetime import datetime, timezone as _tz
            event = RawCarrierEvent(
                carrier_id=carrier_code.lower(),
                tracking_id=outcome.tracking_id,
                raw_code=raw_code,
                raw_description=None,
                raw_payload=raw_payload,
                api_version=api_version,
                event_at=datetime.now(_tz.utc),
            )
            normalized = await StatusNormalizer(tenant_id=self.tenant_id).normalize(event)
            normalized_canonical = normalized.canonical_status
            normalized_incident = normalized.incident_type
            outcome.canonical_status = normalized_canonical
            outcome.incident_type = normalized_incident

        guia = await self.guias.find_one({"id": outcome.guia_id})
        if not guia:
            return
        wf_outcome = await WorkflowEngine(tenant_id=self.tenant_id).process_post_ingest(
            guia=guia,
            ingest_action=outcome.action,
            normalized_canonical=normalized_canonical,
            normalized_incident_type=normalized_incident,
        )
        outcome.workflow_action = wf_outcome.action
        outcome.ticket_id = wf_outcome.ticket_id

    # ---------- Layout v2 (CSV / XLSX) ---------------------------------
    async def process_layout_file(
        self, *, client_id: str, file_bytes: bytes, filename: str,
    ) -> dict:
        """Layout v2 (Iter39) — Acepta CSV o XLSX con 36 columnas en español.

        Reemplaza el `process_csv` v1 (5 columnas mínimas). Las columnas
        canónicas viven en `services.ingest.layout_v2.LAYOUT_V2_HEADERS`.
        """
        # Lazy import para no romper tests que no necesitan openpyxl.
        from services.ingest.layout_v2 import (  # noqa: PLC0415
            detect_and_parse, normalize_row, LAYOUT_V2_HEADERS,
        )

        summary = {"created": 0, "updated": 0, "discarded_terminal": 0,
                   "discarded_no_change": 0, "errors": 0, "rows": 0}
        errors: list[dict] = []

        try:
            rows = detect_and_parse(file_bytes, filename)
        except ValueError as e:
            raise ValueError(str(e))

        # Pre-flight: validamos al menos que el archivo tenga al menos 1 fila.
        rows = list(rows)
        if not rows:
            return {
                "summary": summary, "errors": [],
                "layout_version": "v2",
                "expected_headers": LAYOUT_V2_HEADERS,
            }

        for i, raw_row in enumerate(rows, start=2):
            summary["rows"] += 1
            try:
                norm = normalize_row(raw_row, line_no=i)
                outcome = await self.process_event(
                    client_id=client_id,
                    tracking_id=norm["tracking_id"],
                    carrier_code=norm["carrier_code"],
                    carrier_status=norm["carrier_status"],
                    carrier_status_description=norm["carrier_status_description"],
                    raw_code=norm["raw_code"],
                    event_at=norm["event_at"],
                    source="layout",
                    carrier_meta=norm["carrier_meta"],
                    sender=norm["sender"],
                    recipient=norm["recipient"],
                    service=norm["service"],
                    weights=norm["weights"],
                    declared_value=norm["declared_value"],
                    insurance_purchased=norm["insurance_purchased"],
                    delivery_notes=norm["delivery_notes"],
                    carrier_incidence=norm["carrier_incidence"],
                    external_tms_client_id=norm["external_tms_client_id"],
                    external_reference=norm["external_reference"],
                    delivered_at_external=norm["delivered_at_external"],
                    shipped_at_external=norm["shipped_at_external"],
                    created_at_external=norm["created_at_external"],
                )
                summary[outcome.action] += 1
            except Exception as e:  # noqa: BLE001
                summary["errors"] += 1
                errors.append({
                    "line": i, "error": str(e),
                    "tracking_id": (raw_row or {}).get("Tracking") if isinstance(raw_row, dict) else None,
                })
        return {"summary": summary, "errors": errors, "layout_version": "v2"}

    # ---------- Layout v1 (compat fallback, deprecado) -----------------
    async def process_csv(self, *, client_id: str, file_bytes: bytes) -> dict:
        """[DEPRECATED Iter39] Layout v1 minimalista. Mantener temporalmente
        para no romper tests legacy. Usar `process_layout_file` para v2.
        """
        text = file_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        required = {"tracking_id", "carrier_code", "carrier_status"}
        missing = required - set([h.strip() for h in (reader.fieldnames or [])])
        if missing:
            raise ValueError(f"CSV faltan columnas obligatorias: {', '.join(sorted(missing))}")

        summary = {"created": 0, "updated": 0, "discarded_terminal": 0,
                   "discarded_no_change": 0, "errors": 0, "rows": 0}
        errors: list[dict] = []
        for i, row in enumerate(reader, start=2):  # row 1 is header
            summary["rows"] += 1
            try:
                outcome = await self.process_event(
                    client_id=client_id,
                    tracking_id=row["tracking_id"].strip(),
                    carrier_code=row["carrier_code"].strip(),
                    carrier_status=row["carrier_status"].strip(),
                    carrier_status_description=(row.get("carrier_status_description") or "").strip() or None,
                    raw_code=(row.get("raw_code") or "").strip() or None,
                    event_at=(row.get("event_at") or "").strip() or None,
                    source="layout",
                )
                summary[outcome.action] += 1
            except Exception as e:  # noqa: BLE001
                summary["errors"] += 1
                errors.append({"line": i, "error": str(e), "tracking_id": row.get("tracking_id")})
        return {"summary": summary, "errors": errors}

    # ---------- Pulling stub -------------------------------------------
    async def trigger_pull(self, *, client_id: str,
                            date_from: str | None = None,
                            date_to: str | None = None) -> dict:
        """Manual pull. Iter56 — soporta rango opcional `date_from`/`date_to`
        (ISO date strings, ej. "2026-05-01"). Cuando hay rango, ejecuta el
        pull real contra el carrier configurado del cliente y devuelve
        métricas. Sin rango, mantiene el comportamiento legacy (log + meta).
        """
        client = await self.clients.find_one({"id": client_id})
        if not client:
            raise ResourceNotFoundException("Cliente no encontrado.")
        log.info("pull_attempt", extra={"context": {
            "tenant_id": self.tenant_id, "client_id": client_id,
            "ingest_mode": client.get("ingest_mode"),
            "api_url": client.get("api_url"),
            "date_from": date_from, "date_to": date_to,
        }})
        if date_from or date_to:
            return await self._pull_range(
                client=client, date_from=date_from, date_to=date_to)
        return {
            "client_id": client_id,
            "ingest_mode": client.get("ingest_mode"),
            "api_url": client.get("api_url"),
            "api_creds_set": bool(client.get("api_creds_ref")),
            "pulling_freq_min": client.get("pulling_freq_min"),
            "result": "pull_attempt_logged",
            "note": "Sin rango: ping de configuración. Para cargar datos, "
                    "selecciona date_from + date_to.",
        }

    async def _pull_range(self, *, client: dict,
                          date_from: str | None,
                          date_to: str | None) -> dict:
        """Iter56 — pull real para Routal (único carrier con bulk-listing).

        Layout esperado en `client`:
          - `client.carriers.<code>.{api_key_ref, project_ids, default_project_id,
                                     base_url, enabled}`  ← layout actual (iter56.1)
          - Legacy: `client.carrier` + `client.routal.project_ids`  ← compat.

        - Lista planes en el rango (filtro local por `created_at`).
        - Para cada plan, lista stops y los convierte a `RawCarrierEvent`.
        - Cada stop → `process_event()` (idempotente por tracking_id).
        - Retorna métricas + errores (max 50).
        """
        from services.cae.adapters.routal import RoutalAdapter
        from repositories.platform_carriers import PlatformCarrierRepository

        # Detección de carrier: el cliente puede declarar `carriers.<code>`
        # (layout actual) o `carrier` (legacy). Buscamos routal explícitamente.
        carriers_cfg = client.get("carriers") or {}
        routal_cfg = carriers_cfg.get("routal") or {}
        legacy_routal = client.get("routal") or {}
        carrier_legacy = (client.get("carrier") or "").lower()
        is_routal = bool(routal_cfg) or carrier_legacy == "routal" or bool(legacy_routal)
        if not is_routal:
            return {"result": "unsupported_carrier",
                    "note": f"Pull en rango solo disponible para Routal. "
                            f"Cliente no tiene `carriers.routal` configurado.",
                    "client_id": client["id"]}

        # Normalizar a ISO completo (inicio del día / fin del día)
        from_iso = f"{date_from}T00:00:00.000Z" if date_from and "T" not in date_from else date_from
        to_iso = f"{date_to}T23:59:59.999Z" if date_to and "T" not in date_to else date_to

        # Resolver credenciales con jerarquía: PLATFORM primero (modelo
        # multi-tenant, key compartida) → cliente.carriers.routal override →
        # cliente.routal (legacy).
        platform_repo = PlatformCarrierRepository()
        platform_cfg = await platform_repo.get_decrypted("routal") or {}
        platform_key = platform_cfg.get("api_key")

        # Decryptamos la client key (si existe) como posible override
        client_key = None
        if routal_cfg.get("api_key_ref"):
            try:
                from core.crypto import decrypt
                client_key = decrypt(routal_cfg["api_key_ref"])
            except Exception:  # noqa: BLE001
                client_key = None
        client_key = client_key or legacy_routal.get("api_key")

        # Preferimos la **más larga** (las keys reales de Routal son >=20 chars;
        # un placeholder corto en cliente no debe pisar la key real de plataforma).
        api_key = platform_key
        if client_key and len(client_key) >= 20:
            api_key = client_key

        base_url = (routal_cfg.get("base_url") or legacy_routal.get("base_url")
                    or client.get("api_url") or platform_cfg.get("base_url"))
        project_ids = (routal_cfg.get("project_ids")
                       or legacy_routal.get("project_ids")
                       or platform_cfg.get("project_ids") or [])

        if not api_key:
            return {"result": "no_credentials",
                    "note": "Falta api_key en cliente.carriers.routal o plataforma."}
        if not project_ids:
            return {"result": "no_project_ids",
                    "note": "Falta `project_ids` en cliente.carriers.routal."}

        adapter = RoutalAdapter(
            api_key=api_key, base_url=base_url,
            project_ids=project_ids,
        )

        summary = {"plans": 0, "stops_seen": 0, "guias_processed": 0,
                   "errors": 0}
        errors: list[dict] = []

        # Iter56.1 — procesar projects en paralelo (asyncio.gather) y limitar
        # cada project a `max_plans_per_project` planes (default 50). El timeout
        # del proxy es 60s; queremos terminar en <50s para clientes con N projects.
        import asyncio as _asyncio
        max_plans_per_project = 50

        async def _process_project(pid: str) -> dict:
            local = {"plans": 0, "stops": 0, "guias": 0, "errs": 0,
                     "err_list": []}
            try:
                plans = await adapter.list_recent_plans(
                    project_id=pid, limit=max_plans_per_project,
                    created_from=from_iso, created_to=to_iso,
                )
            except Exception as e:  # noqa: BLE001
                local["err_list"].append({"phase": "list_plans",
                                          "project_id": pid,
                                          "error": str(e)[:200]})
                return local
            local["plans"] = len(plans)

            for plan in plans:
                plan_id = plan.get("_id") or plan.get("id")
                if not plan_id:
                    continue
                try:
                    stops = await adapter.list_stops_in_plan(plan_id)
                except Exception as e:  # noqa: BLE001
                    local["err_list"].append({"phase": "list_stops",
                                              "plan_id": plan_id,
                                              "error": str(e)[:200]})
                    continue
                local["stops"] += len(stops)

                # Procesar stops del plan concurrentemente (max 10 a la vez)
                sem = _asyncio.Semaphore(10)

                async def _process_stop(stop: dict):
                    async with sem:
                        tracking_id = (stop.get("external_id")
                                       or stop.get("tracking_id")
                                       or stop.get("_id"))
                        if not tracking_id:
                            return
                        try:
                            stop["_routal_project_id"] = pid
                            event = adapter._stop_to_event(str(tracking_id), stop)
                            await self.process_event(
                                client_id=client["id"],
                                tracking_id=str(tracking_id),
                                carrier_code="routal",
                                carrier_status=event.raw_description or event.raw_code,
                                carrier_status_description=event.raw_description,
                                raw_code=event.raw_code,
                                api_version="v2",
                                event_at=event.event_at.isoformat() if event.event_at else None,
                                raw_payload=event.raw_payload or {},
                                source="pull",
                            )
                            local["guias"] += 1
                        except Exception as e:  # noqa: BLE001
                            local["errs"] += 1
                            if len(local["err_list"]) < 10:
                                local["err_list"].append({
                                    "phase": "process_event",
                                    "tracking_id": str(tracking_id),
                                    "error": str(e)[:200],
                                })

                await _asyncio.gather(*[_process_stop(s) for s in stops])
            return local

        # Ejecutar todos los projects en paralelo
        results = await _asyncio.gather(*[_process_project(pid)
                                          for pid in project_ids])
        for r in results:
            summary["plans"] += r["plans"]
            summary["stops_seen"] += r["stops"]
            summary["guias_processed"] += r["guias"]
            summary["errors"] += r["errs"]
            if r["err_list"]:
                errors.extend(r["err_list"][:max(0, 50 - len(errors))])
        return {
            "client_id": client["id"],
            "carrier_code": "routal",
            "date_from": date_from,
            "date_to": date_to,
            "summary": summary,
            "errors": errors,
            "result": "pull_range_completed",
        }
