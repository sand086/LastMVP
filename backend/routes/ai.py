"""Routes IA — PROMPT 26.

Públicas (autenticadas):
  POST /api/ai/invoke                                  agent+

Admin (admin+ / superadmin / root_dev según endpoint):
  GET    /api/admin/ai/features                        admin+ (lectura)
  POST   /api/admin/ai/features                        root_dev | superadmin
  PATCH  /api/admin/ai/features/{id}                   root_dev | superadmin
  DELETE /api/admin/ai/features/{id}                   root_dev | superadmin   (soft → active=false)

  GET    /api/admin/ai/brackets                        admin+
  POST   /api/admin/ai/brackets                        root_dev | superadmin
  PATCH  /api/admin/ai/brackets/{id}                   root_dev | superadmin

  GET    /api/admin/ai/client-config                   admin+
  GET    /api/admin/ai/client-config/{client_id}       admin+
  PUT    /api/admin/ai/client-config                   admin+ (upsert opt-in)
  PATCH  /api/admin/ai/client-config/{client_id}/opt-out  admin+

  GET    /api/admin/ai/consumption                     admin+ (dashboard)
  GET    /api/admin/ai/invocation-log                  admin+
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Query, Request

from core.errors import ResourceNotFoundException
from core.response import fail, ok
from core.uuid import new_id
from middleware.rbac import (
    require_min_role, require_role, resolve_client_scope,
    apply_client_scope_filter,
)
from models.ai import (
    BracketCreate, BracketUpdate,
    ClientConfigUpsert, FeatureCreate, FeatureUpdate, InvokeRequest, OptOutBody,
)
from repositories.ai import (
    AIBracketRepository, AIClientConfigRepository,
    AIConsumptionRepository, AIFeatureRepository,
    AIInvocationLogRepository,
)
from services.ai import gateway as ai_gateway


# ─────────────────────────── /api/ai ─────────────────────────────────────
router_invoke = APIRouter(prefix="/api/ai", tags=["ai"])
_INVOKE_RBAC = require_min_role("agent")


@router_invoke.post("/invoke")
async def invoke_feature(
    payload: InvokeRequest,
    request: Request,
    _: object = Depends(_INVOKE_RBAC),
):
    user = request.state.user
    # Resolver client_id: si viene ticket_id, derivar; si no, requerir client_id explícito
    client_id = payload.input.get("client_id") if isinstance(payload.input, dict) else None
    if not client_id and payload.ticket_id:
        from core.db import get_db
        db = get_db()
        ticket = await db.tickets.find_one(
            {"id": payload.ticket_id, "tenant_id": user.tenant_id},
            {"_id": 0, "client_id": 1},
        )
        if ticket:
            client_id = ticket.get("client_id")
    if not client_id:
        return fail("VALIDATION_FAILED",
                    "Falta client_id (proveer en input.client_id o vía ticket_id válido).",
                    field="client_id")

    result = await ai_gateway.invoke(
        tenant_id=user.tenant_id, client_id=client_id, user_id=user.id,
        feature_code=payload.feature_code, raw_input=payload.input,
        ticket_id=payload.ticket_id,
    )
    if result.ok:
        return ok(result.data)
    # Mapear códigos AI_* a fail estándar (definimos códigos custom para HTTP_STATUS)
    return _ai_fail(result.code, result.message, result.http_status)


@router_invoke.post("/invoke/stream")
async def invoke_feature_stream(
    payload: InvokeRequest,
    request: Request,
    _: object = Depends(_INVOKE_RBAC),
):
    """Streaming SSE — chunks del output a medida que se genera (P1).

    Implementación: como `emergentintegrations.LlmChat.send_message()` retorna
    el texto completo, hacemos chunking artificial token-por-palabra para
    UX progresiva. La invocación se loggea una vez al final.
    """
    from fastapi.responses import StreamingResponse
    user = request.state.user
    client_id = payload.input.get("client_id") if isinstance(payload.input, dict) else None
    if not client_id and payload.ticket_id:
        from core.db import get_db
        db = get_db()
        ticket = await db.tickets.find_one(
            {"id": payload.ticket_id, "tenant_id": user.tenant_id},
            {"_id": 0, "client_id": 1},
        )
        if ticket:
            client_id = ticket.get("client_id")
    if not client_id:
        return fail("VALIDATION_FAILED", "Falta client_id.", field="client_id")

    async def _gen():
        import asyncio
        import json
        result = await ai_gateway.invoke(
            tenant_id=user.tenant_id, client_id=client_id, user_id=user.id,
            feature_code=payload.feature_code, raw_input=payload.input,
            ticket_id=payload.ticket_id,
        )
        if not result.ok:
            yield "event: error\ndata: " + json.dumps({
                "code": result.code, "message": result.message,
            }) + "\n\n"
            return
        text = result.data["output"]["text"]
        # Chunking por palabra (UX progresiva)
        words = text.split(" ")
        for i, w in enumerate(words):
            sep = " " if i < len(words) - 1 else ""
            yield "event: chunk\ndata: " + json.dumps({"text": w + sep}) + "\n\n"
            await asyncio.sleep(0.015)
        meta = {
            "invocation_id": result.data["invocation_id"],
            "draft": result.data["draft"],
            "from_cache": result.data.get("from_cache", False),
            "cost_estimate_usd": result.data["cost_estimate_usd"],
            "model": result.data["model"],
        }
        yield "event: done\ndata: " + json.dumps(meta) + "\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router_invoke.post("/invocations/{invocation_id}/approve")
async def approve_invocation(
    invocation_id: str,
    request: Request,
    _: object = Depends(_INVOKE_RBAC),
):
    """Marca una invocación draft como aprobada (R42 ⇒ humano valida) y
    dispara el webhook saliente si el cliente lo configuró."""
    from core.db import get_db
    user = request.state.user
    db = get_db()
    inv = await db.ai_invocation_log.find_one(
        {"id": invocation_id, "tenant_id": user.tenant_id}, {"_id": 0},
    )
    if not inv:
        raise ResourceNotFoundException()
    if inv.get("status") not in ("success", "cache_hit"):
        return fail("VALIDATION_FAILED",
                    f"No se puede aprobar invocación con status='{inv.get('status')}'.")
    if inv.get("approved_at"):
        return fail("VALIDATION_FAILED", "Esta invocación ya fue aprobada.")

    now = datetime.now(timezone.utc).isoformat()
    await db.ai_invocation_log.update_one(
        {"id": invocation_id, "tenant_id": user.tenant_id},
        {"$set": {"approved_at": now, "approved_by": user.id}},
    )

    # Disparar webhook si destinatario es client_final/both Y cliente tiene URL
    cfg = await AIClientConfigRepository(
        tenant_id=user.tenant_id
    ).get(inv["client_id"])
    delivered = None
    if cfg and cfg.get("webhook_outbound_url") and inv.get("destinatario") in ("client_final", "both"):
        from services.ai.webhook_out import fire_and_forget
        fire_and_forget(
            tenant_id=user.tenant_id, invocation_id=invocation_id,
            url=cfg["webhook_outbound_url"], secret=cfg.get("webhook_outbound_secret"),
            payload={
                "invocation_id": invocation_id,
                "feature_code": inv["feature_code"],
                "ticket_id": inv.get("ticket_id"),
                "client_id": inv["client_id"],
                "approved_by": user.id,
                "approved_at": now,
                "model": inv.get("model"),
                "provider": inv.get("provider"),
                "response_hash": inv.get("response_hash"),
            },
        )
        delivered = "queued"
    return ok({"invocation_id": invocation_id, "approved_at": now,
               "webhook": delivered})


@router_invoke.get("/system/status")
async def ai_system_status(request: Request, _: object = Depends(_INVOKE_RBAC)):
    """Diagnóstico interno — circuit breaker + cache metrics. Sólo lectura."""
    from services.ai.circuit_breaker import breaker
    from services.ai.prompt_cache import cache as prompt_cache
    return ok({
        "breaker": breaker.status_snapshot(),
        "cache_metrics": prompt_cache.metrics,
    })



def _ai_fail(code: str, message: str, http_status: int):
    """Wrapper para devolver códigos AI_* con HTTP status correcto."""
    from fastapi.responses import JSONResponse
    import secrets
    payload = {
        "success": False, "data": None,
        "meta": {"request_id": "req_" + secrets.token_hex(6),
                 "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "errors": [{"code": code, "message": message, "field": None}],
    }
    return JSONResponse(status_code=http_status, content=payload)


# ─────────────────────────── /api/admin/ai ───────────────────────────────
router_admin = APIRouter(prefix="/api/admin/ai", tags=["ai-admin"])
_ADMIN_RBAC = require_min_role("admin")
_SUPER_RBAC = require_role("root_dev", "superadmin")
# PROMPT_27 — read-only audit persona; can read invocation log/consumption,
# preview audit CSV and download it (tenant-scoped).
# Bundle G · G-02 — client_viewer también puede ver el panel read-only
# (sin export CSV: queda gated por _AUDIT_EXPORT_RBAC).
_AUDIT_READ_RBAC = require_role(
    "root_dev", "superadmin", "admin", "client_auditor", "client_viewer",
)
_AUDIT_EXPORT_RBAC = require_role(
    "root_dev", "superadmin", "client_auditor",
)


# ── Features (catálogo) ──────────────────────────────────────────────────
@router_admin.get("/features")
async def list_features(request: Request, _: object = Depends(_ADMIN_RBAC)):
    repo = AIFeatureRepository(tenant_id=request.state.user.tenant_id)
    items = await repo.find({}, limit=200, sort=[("feature_code", 1)])
    return ok({"items": items, "count": len(items)})


@router_admin.post("/features")
async def create_feature(
    body: FeatureCreate, request: Request, _: object = Depends(_SUPER_RBAC),
):
    user = request.state.user
    repo = AIFeatureRepository(tenant_id=user.tenant_id)
    if await repo.by_code(body.feature_code):
        return fail("VALIDATION_FAILED",
                    f"Ya existe una feature con code='{body.feature_code}'.",
                    field="feature_code")
    doc = await repo.insert({**body.model_dump(), "id": new_id()})
    return ok(doc, status_code=201)


@router_admin.patch("/features/{feature_id}")
async def update_feature(
    feature_id: str, body: FeatureUpdate, request: Request, _: object = Depends(_SUPER_RBAC),
):
    repo = AIFeatureRepository(tenant_id=request.state.user.tenant_id)
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return fail("VALIDATION_FAILED", "Sin campos para actualizar.")
    if await repo.update_by_id(feature_id, updates) == 0:
        raise ResourceNotFoundException()
    doc = await repo.find_one({"id": feature_id})
    return ok(doc)


@router_admin.delete("/features/{feature_id}")
async def deactivate_feature(
    feature_id: str, request: Request, _: object = Depends(_SUPER_RBAC),
):
    repo = AIFeatureRepository(tenant_id=request.state.user.tenant_id)
    if await repo.update_by_id(feature_id, {"active": False}) == 0:
        raise ResourceNotFoundException()
    return ok({"id": feature_id, "active": False})


# ── Brackets ─────────────────────────────────────────────────────────────
@router_admin.get("/brackets")
async def list_brackets(_: object = Depends(_ADMIN_RBAC)):
    repo = AIBracketRepository()
    items = await repo.list_all()
    return ok({"items": items, "count": len(items)})


@router_admin.post("/brackets")
async def create_bracket(body: BracketCreate, _: object = Depends(_SUPER_RBAC)):
    repo = AIBracketRepository()
    if await repo.by_name(body.bracket_name):
        return fail("VALIDATION_FAILED",
                    f"Ya existe bracket '{body.bracket_name}'.", field="bracket_name")
    doc = await repo.insert(body.model_dump())
    return ok(doc, status_code=201)


@router_admin.patch("/brackets/{bracket_id}")
async def update_bracket(bracket_id: str, body: BracketUpdate, _: object = Depends(_SUPER_RBAC)):
    repo = AIBracketRepository()
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return fail("VALIDATION_FAILED", "Sin campos para actualizar.")
    result = await repo.col.update_one({"id": bracket_id}, {"$set": updates})
    if result.modified_count == 0:
        raise ResourceNotFoundException()
    doc = await repo.col.find_one({"id": bracket_id}, {"_id": 0})
    return ok(doc)


# ── Client config (opt-in / opt-out) ─────────────────────────────────────
@router_admin.get("/client-config")
async def list_client_configs(request: Request, _: object = Depends(_ADMIN_RBAC)):
    repo = AIClientConfigRepository(tenant_id=request.state.user.tenant_id)
    # Ocultar la clave cifrada y el secret del webhook del response
    items = await repo.find({}, projection={
        "_id": 0, "custom_api_key_encrypted": 0, "webhook_outbound_secret": 0,
    }, limit=500, sort=[("client_id", 1)])
    # Marcar presencia de secret
    for it in items:
        it["webhook_outbound_secret_set"] = bool(it.pop("webhook_outbound_secret_present", False) or it.get("webhook_outbound_url"))
    return ok({"items": items, "count": len(items)})


@router_admin.get("/client-config/{client_id}")
async def get_client_config(client_id: str, request: Request, _: object = Depends(_ADMIN_RBAC)):
    repo = AIClientConfigRepository(tenant_id=request.state.user.tenant_id)
    doc = await repo.col.find_one(
        repo._scope({"client_id": client_id}),
        {"_id": 0, "custom_api_key_encrypted": 0, "webhook_outbound_secret": 0},
    )
    if not doc:
        raise ResourceNotFoundException()
    doc["webhook_outbound_secret_set"] = bool(doc.pop("webhook_outbound_secret_present", False) or doc.get("webhook_outbound_url"))
    return ok(doc)


@router_admin.put("/client-config")
async def upsert_client_config(
    body: ClientConfigUpsert, request: Request, _: object = Depends(_ADMIN_RBAC),
):
    user = request.state.user
    # Validar bracket si se especifica
    if body.bracket_id:
        if not await AIBracketRepository().find_one({"id": body.bracket_id}):
            return fail("VALIDATION_FAILED",
                        "Bracket no existe.", field="bracket_id")
    # Validar features
    feat_repo = AIFeatureRepository(tenant_id=user.tenant_id)
    for code in body.enabled_features:
        if not await feat_repo.by_code(code):
            return fail("VALIDATION_FAILED",
                        f"Feature '{code}' no existe en catálogo.", field="enabled_features")

    # Validar cliente existe en este tenant
    from core.db import get_db
    db = get_db()
    if not await db.clients.find_one(
        {"id": body.client_id, "tenant_id": user.tenant_id}, {"_id": 0, "id": 1}
    ):
        raise ResourceNotFoundException("Cliente no encontrado")

    payload = body.model_dump(exclude={"custom_api_key"})
    # R39 — opt-in requiere firma
    if body.is_active and not body.opt_in_signature:
        return fail("VALIDATION_FAILED",
                    "Activar IA requiere opt_in_signature (R39).",
                    field="opt_in_signature")
    if body.is_active:
        payload["opt_in_at"] = datetime.now(timezone.utc).isoformat()
        payload["opt_out_at"] = None
        payload["opt_out_reason"] = None

    if body.custom_api_key:
        payload["custom_api_key_encrypted"] = ai_gateway.encrypt_custom_key(body.custom_api_key)
        payload["custom_api_key_present"] = True
    elif body.custom_api_key == "":
        payload["custom_api_key_encrypted"] = None
        payload["custom_api_key_present"] = False

    repo = AIClientConfigRepository(tenant_id=user.tenant_id)
    doc = await repo.upsert(payload)
    # Strip secretos del response
    has_secret = bool(doc.get("webhook_outbound_secret"))
    doc = {k: v for k, v in doc.items()
           if k not in ("custom_api_key_encrypted", "webhook_outbound_secret")}
    doc["webhook_outbound_secret_set"] = has_secret or bool(doc.get("webhook_outbound_url"))
    return ok(doc)


@router_admin.patch("/client-config/{client_id}/opt-out")
async def opt_out_client(
    client_id: str, body: OptOutBody, request: Request, _: object = Depends(_ADMIN_RBAC),
):
    user = request.state.user
    repo = AIClientConfigRepository(tenant_id=user.tenant_id)
    if not await repo.opt_out(client_id, body.reason):
        raise ResourceNotFoundException()
    # Log explícito en ai_invocation_log (P0.10)
    log_repo = AIInvocationLogRepository(tenant_id=user.tenant_id)
    await log_repo.append({
        "client_id": client_id, "user_id": user.id,
        "feature_id": "opt_out_event", "feature_code": "opt_out",
        "ticket_id": None, "provider": "anthropic", "model": "",
        "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0.0, "cost_mxn": 0.0, "exchange_rate": 0.0,
        "latency_ms": 0,
        "prompt_hash": "", "prompt_masked_preview": body.reason[:500],
        "response_hash": "",
        "status": "opt_out_executed", "error_code": None,
        "request_id": new_id(),
    })
    return ok({"client_id": client_id, "is_active": False, "reason": body.reason})


# ── Dashboard de consumo ─────────────────────────────────────────────────
@router_admin.get("/consumption")
async def consumption_dashboard(
    request: Request,
    client_id: str | None = Query(default=None),
    year_month: str | None = Query(default=None),
    _: object = Depends(_AUDIT_READ_RBAC),
):
    repo = AIConsumptionRepository(tenant_id=request.state.user.tenant_id)
    q: dict = {}
    # Bundle G+H — aplicar scope multi-cliente
    apply_client_scope_filter(q, request.state.user, client_id)
    if year_month:
        q["year_month"] = year_month
    items = await repo.find(q, limit=500, sort=[("year_month", -1), ("client_id", 1)])
    return ok({"items": items, "count": len(items)})


@router_admin.get("/cost-trend")
async def cost_per_feature_trend(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    client_id: str | None = Query(default=None),
    _: object = Depends(_AUDIT_READ_RBAC),
):
    """Tendencia diaria de costo USD por feature_code en los últimos `days` días.

    Retorna:
      {
        "days": 30,
        "series": [
            {"feature_code": "classify_motivo", "total_cost_usd": 1.245,
             "total_invocations": 45,
             "points": [{"date": "2026-04-10", "cost_usd": 0.05, "invocations": 2}, …]},
            …
        ],
        "totals_by_day": [{"date": "...", "cost_usd": ..., "invocations": ...}, …],
        "grand_total_usd": 5.43,
      }
    """
    from datetime import datetime, timezone, timedelta
    from core.db import get_db
    db = get_db()
    user = request.state.user
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    match: dict = {
        "tenant_id": user.tenant_id,
        "created_at": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        "status": {"$ne": "error"},
    }
    # Bundle G+H — scope multi-cliente
    apply_client_scope_filter(match, user, client_id)

    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_date": {"$substr": ["$created_at", 0, 10]},
        }},
        {"$group": {
            "_id": {"feature_code": "$feature_code", "date": "$_date"},
            "cost_usd": {"$sum": {"$ifNull": ["$cost_usd", 0]}},
            "invocations": {"$sum": 1},
        }},
        {"$sort": {"_id.date": 1}},
    ]
    rows: list[dict] = []
    async for row in db.ai_invocation_log.aggregate(pipeline):
        rows.append({
            "feature_code": row["_id"]["feature_code"] or "unknown",
            "date": row["_id"]["date"],
            "cost_usd": round(float(row["cost_usd"]), 6),
            "invocations": int(row["invocations"]),
        })

    # Reshape into series-per-feature
    by_feature: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    grand_total = 0.0
    for r in rows:
        fc = r["feature_code"]
        d = r["date"]
        s = by_feature.setdefault(fc, {
            "feature_code": fc, "total_cost_usd": 0.0,
            "total_invocations": 0, "points": [],
        })
        s["points"].append({
            "date": d, "cost_usd": r["cost_usd"],
            "invocations": r["invocations"],
        })
        s["total_cost_usd"] = round(s["total_cost_usd"] + r["cost_usd"], 6)
        s["total_invocations"] += r["invocations"]
        # Totales del día
        td = by_day.setdefault(d, {"date": d, "cost_usd": 0.0, "invocations": 0})
        td["cost_usd"] = round(td["cost_usd"] + r["cost_usd"], 6)
        td["invocations"] += r["invocations"]
        grand_total += r["cost_usd"]

    series = sorted(by_feature.values(),
                     key=lambda x: x["total_cost_usd"], reverse=True)
    totals_by_day = sorted(by_day.values(), key=lambda x: x["date"])
    return ok({
        "days": days,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "series": series,
        "totals_by_day": totals_by_day,
        "grand_total_usd": round(grand_total, 6),
        "features_count": len(series),
    })


@router_admin.get("/invocation-log")
async def invocation_log(
    request: Request,
    client_id: str | None = Query(default=None),
    feature_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(_AUDIT_READ_RBAC),
):
    repo = AIInvocationLogRepository(tenant_id=request.state.user.tenant_id)
    q: dict = {}
    # Bundle G+H — scope multi-cliente
    apply_client_scope_filter(q, request.state.user, client_id)
    if feature_code:
        q["feature_code"] = feature_code
    if status:
        q["status"] = status
    items = await repo.query(q, limit=limit)
    return ok({"items": items, "count": len(items)})



# ── Benchmark cost-vs-latency (P2) ───────────────────────────────────────
@router_admin.post("/benchmark/run")
async def run_benchmark_endpoint(
    request: Request,
    dry_run: bool = Query(default=True),
    samples: int = Query(default=3, ge=1, le=10),
    _: object = Depends(_SUPER_RBAC),
):
    """Ejecuta benchmark cost-vs-latency contra todos los modelos del catálogo.

    `dry_run=true` (default): NO gasta tokens, estima desde MODEL_PRICING.
    `dry_run=false`:           ejecuta `samples` invocaciones reales por modelo.
                               Sólo root_dev|superadmin (gasta tokens).
    """
    from services.ai.benchmark import run_benchmark
    user = request.state.user
    doc = await run_benchmark(
        dry_run=dry_run, samples=samples, triggered_by=user.id,
    )
    return ok(doc)


@router_admin.get("/benchmark")
async def list_benchmarks_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    _: object = Depends(_ADMIN_RBAC),
):
    from services.ai.benchmark import list_benchmarks
    items = await list_benchmarks(limit=limit)
    return ok({"items": items, "count": len(items)})


# ── Audit export con firma HMAC (P2) ─────────────────────────────────────
@router_admin.get("/audit/export.csv")
async def audit_export_csv(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    feature_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=100_000),
    _: object = Depends(_AUDIT_EXPORT_RBAC),
):
    """Genera CSV firmado con HMAC SHA-256 para auditoría externa.

    Header `X-MyE-Audit-Signature: sha256=<hex>` permite a un auditor verificar
    que el body no fue modificado tras la exportación.
    """
    from fastapi.responses import Response
    from services.ai.audit_export import build_csv
    user = request.state.user
    # Bundle G+H — scope multi-cliente (puede ser str o list[str])
    scoped_cid = resolve_client_scope(user, client_id)
    body, meta = await build_csv(
        tenant_id=user.tenant_id,
        date_from=date_from, date_to=date_to,
        client_id=scoped_cid, feature_code=feature_code,
        status=status, limit=limit,
    )
    filename = f"ai-audit-{user.tenant_id[:8]}-{meta['exported_at'][:10]}.csv"
    # Auditor attestation — append-only log de QUIÉN descargó QUÉ
    try:
        from repositories.ai_audit_attestations import AIAuditAttestationRepository
        await AIAuditAttestationRepository(tenant_id=user.tenant_id).record_download(
            user_id=user.id, signature=meta["signature"], rows=meta["rows"],
            filters={"date_from": date_from, "date_to": date_to,
                     "client_id": client_id, "feature_code": feature_code,
                     "status": status, "limit": limit},
            ip=request.client.host if request.client else None,
        )
    except Exception:  # noqa: BLE001
        from core.logger import log
        log.exception("audit_attestation_download_failed")
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-MyE-Audit-Signature": meta["signature"],
            "X-MyE-Audit-Rows": str(meta["rows"]),
            "X-MyE-Audit-Exported-At": meta["exported_at"],
        },
    )


@router_admin.post("/audit/attest")
async def audit_attest(
    request: Request,
    payload: dict = Body(...),
    _: object = Depends(_AUDIT_READ_RBAC),
):
    """Atestación voluntaria del auditor — 'He revisado este lote'.

    Body:
      - signature: str (la firma HMAC del CSV/preview que se está atestando)
      - rows: int
      - filters: dict (los mismos filtros usados al descargar)
      - comment: str (≤500 chars)
    """
    user = request.state.user
    sig = (payload.get("signature") or "").strip()
    rows = int(payload.get("rows") or 0)
    comment = (payload.get("comment") or "").strip()
    if not sig.startswith("sha256="):
        return fail("VALIDATION_FAILED", "signature debe ser 'sha256=...'")
    if not comment:
        return fail("VALIDATION_FAILED", "comment es requerido para atestación.")

    from repositories.ai_audit_attestations import AIAuditAttestationRepository
    repo = AIAuditAttestationRepository(tenant_id=user.tenant_id)
    doc = await repo.record_review(
        user_id=user.id, signature=sig, rows=rows, comment=comment,
        filters=payload.get("filters") or {},
        ip=request.client.host if request.client else None,
    )
    return ok({
        "attestation_id": doc["id"],
        "signature": sig,
        "kind": "review_attestation",
        "user_id": user.id,
        "comment": doc["comment"],
        "created_at": doc["created_at"],
    })


@router_admin.get("/audit/attestations")
async def audit_attestations(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(_AUDIT_READ_RBAC),
):
    """Lista las atestaciones recientes (descargas + reviews) — append-only."""
    user = request.state.user
    from repositories.ai_audit_attestations import AIAuditAttestationRepository
    repo = AIAuditAttestationRepository(tenant_id=user.tenant_id)
    items = await repo.list_recent(limit=limit)
    return ok({"items": items, "count": len(items)})


@router_admin.get("/audit/preview")
async def audit_preview(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    feature_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=100_000),
    _: object = Depends(_AUDIT_READ_RBAC),
):
    """Preview JSON del export — devuelve metadata + signature + sample del CSV (primeras 5 filas)."""
    from services.ai.audit_export import build_csv
    user = request.state.user
    # Bundle G+H — scope multi-cliente (puede ser str o list[str])
    scoped_cid = resolve_client_scope(user, client_id)
    body, meta = await build_csv(
        tenant_id=user.tenant_id,
        date_from=date_from, date_to=date_to,
        client_id=scoped_cid, feature_code=feature_code,
        status=status, limit=limit,
    )
    text = body.decode("utf-8")
    preview_lines = text.split("\n")[:6]
    return ok({
        "rows": meta["rows"],
        "signature": meta["signature"],
        "exported_at": meta["exported_at"],
        "filters": meta["filters"],
        "columns": meta["columns"],
        "preview_csv": "\n".join(preview_lines),
        "size_bytes": len(body),
    })
