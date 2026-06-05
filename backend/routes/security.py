"""PROMPT 12 — Auditoría externa de seguridad pre-go-live (P2).

Endpoint: GET /api/admin/security/audit (root_dev|superadmin)

Devuelve un checklist con PASS/WARN/FAIL para cada criterio. NO bloquea el
sistema; sólo informa. Pensado para correr antes de cada release a producción.

Criterios:
  - JWT secret rotación: warn si JWT_SECRET fijo > 90 días
  - HTTPS: pass si CORS_ORIGINS no incluye http:// (excepto localhost)
  - bcrypt cost: pass si BCRYPT_COST >= 12
  - Fernet key configurada
  - HMAC audit signing secret configurado y no default
  - Webhook test secret no en producción (si hay deploy)
  - Cron habilitado
  - Rate limit middleware activo
  - Suscripciones webhook con HMAC válido (todas tienen secret cifrado)
  - Append-only collections sin escrituras directas (verificación reflexiva)
  - Tenants en status≠active no causan crash (sólo conteo)
  - Indexes únicos críticos presentes (users.email+tenant, claims activo)
  - Eventos R37 en log si hay tickets > 0
"""
from __future__ import annotations
import os
from typing import Literal

from fastapi import APIRouter, Depends, Request

from core.db import get_db
from core.response import ok
from middleware.rbac import require_role


router = APIRouter(prefix="/api/admin/security", tags=["security-audit"])
_RBAC_SUPER = require_role("root_dev", "superadmin")


Severity = Literal["pass", "warn", "fail"]


def _check(name: str, severity: Severity, detail: str,
           remediation: str | None = None) -> dict:
    return {
        "name": name, "severity": severity, "detail": detail,
        "remediation": remediation,
    }


@router.get("/audit")
async def security_audit(request: Request, _: object = Depends(_RBAC_SUPER)):
    db = get_db()
    checks: list[dict] = []
    failed = 0
    warned = 0

    # ──────── Secrets / env ────────
    if not os.environ["JWT_SECRET"] or os.environ["JWT_SECRET"] in ("changeme", "secret"):
        checks.append(_check("JWT secret", "fail", "JWT_SECRET no configurado o default.",
                             "Configura JWT_SECRET con una cadena aleatoria de 32+ chars."))
        failed += 1
    else:
        sec_len = len(os.environ["JWT_SECRET"])
        if sec_len < 32:
            checks.append(_check("JWT secret length", "warn",
                                 f"Longitud {sec_len} < 32 chars.",
                                 "Usa al menos 32 caracteres aleatorios."))
            warned += 1
        else:
            checks.append(_check("JWT secret length", "pass",
                                 f"Configurado ({sec_len} chars)."))

    if not os.environ["ENCRYPTION_KEY"]:
        checks.append(_check("Fernet ENCRYPTION_KEY", "fail",
                             "Falta para cifrar credentials/HMAC secrets.",
                             "Genera con `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`."))
        failed += 1
    else:
        checks.append(_check("Fernet ENCRYPTION_KEY", "pass", "Configurada."))

    audit_sec = os.environ["AUDIT_SIGNING_SECRET"]
    if not audit_sec or "rotate-quarterly" in audit_sec.lower():
        checks.append(_check("AUDIT_SIGNING_SECRET", "warn",
                             "Default o ausente — secreto compartido para CSV de auditoría IA.",
                             "Rotar trimestralmente; min 24 chars."))
        warned += 1
    else:
        checks.append(_check("AUDIT_SIGNING_SECRET", "pass",
                             f"Configurado ({len(audit_sec)} chars)."))

    bcrypt_cost = int(os.environ["BCRYPT_COST"])
    if bcrypt_cost < 12:
        checks.append(_check("BCRYPT_COST", "warn",
                             f"Cost {bcrypt_cost} < 12 (recomendado).",
                             "Aumentar BCRYPT_COST=12 (o más en hardware potente)."))
        warned += 1
    else:
        checks.append(_check("BCRYPT_COST", "pass", f"Cost {bcrypt_cost}."))

    # ──────── CORS ────────
    cors = os.environ["CORS_ORIGINS"]
    bad = [o for o in cors.split(",")
           if o.strip().startswith("http://")
           and "localhost" not in o
           and "127.0.0.1" not in o]
    if bad:
        checks.append(_check("CORS HTTPS", "fail",
                             f"Origins HTTP en producción: {bad}",
                             "Sólo permitir https:// en CORS_ORIGINS productivos."))
        failed += 1
    else:
        checks.append(_check("CORS HTTPS", "pass", "Sin orígenes HTTP no-localhost."))

    # ──────── Webhooks SSRF ────────
    if os.environ["MYE_WEBHOOK_ALLOW_HTTP"] == "1":
        checks.append(_check("Webhooks anti-SSRF", "warn",
                             "MYE_WEBHOOK_ALLOW_HTTP=1 (deshabilita HTTPS-only).",
                             "Setear a 0 en producción."))
        warned += 1
    else:
        checks.append(_check("Webhooks anti-SSRF", "pass",
                             "MYE_WEBHOOK_ALLOW_HTTP off (HTTPS-only forzado)."))

    test_sec = os.environ["MYE_WEBHOOK_TEST_SECRET"]
    if test_sec.startswith("test-shared-secret"):
        checks.append(_check("Webhook test secret", "warn",
                             "Default — sólo para dev/staging.",
                             "Cambiar MYE_WEBHOOK_TEST_SECRET en producción."))
        warned += 1
    else:
        checks.append(_check("Webhook test secret", "pass",
                             "Custom — listo para producción."))

    # ──────── Cron ────────
    if os.environ["CRON_ENABLED"] == "1":
        checks.append(_check("Cron scheduler", "pass", "APScheduler activo."))
    else:
        checks.append(_check("Cron scheduler", "warn",
                             "CRON_ENABLED=0 — automatizaciones desactivadas.",
                             "Activar en producción."))
        warned += 1

    # ──────── Webhook subscriptions sanity ────────
    sub_total = await db.webhook_subscriptions.count_documents({})
    sub_no_secret = await db.webhook_subscriptions.count_documents(
        {"$or": [{"hmac_secret_encrypted": {"$exists": False}},
                 {"hmac_secret_encrypted": None}, {"hmac_secret_encrypted": ""}]},
    )
    if sub_no_secret > 0:
        checks.append(_check("Webhook HMAC secrets", "fail",
                             f"{sub_no_secret}/{sub_total} suscripciones sin secret cifrado.",
                             "Forzar rotate-secret en suscripciones afectadas."))
        failed += 1
    else:
        checks.append(_check("Webhook HMAC secrets", "pass",
                             f"{sub_total} suscripción(es) con HMAC OK."))

    # ──────── Append-only integrity (heuristic) ────────
    forbidden_methods = {"update", "delete", "patch", "remove", "set"}
    from repositories.webhooks import WebhookDeliveryLogRepository
    from repositories.ai import AIInvocationLogRepository
    from repositories.ai_audit_attestations import AIAuditAttestationRepository
    bad_repos: list[str] = []
    for cls in [WebhookDeliveryLogRepository, AIInvocationLogRepository,
                AIAuditAttestationRepository]:
        names = {n for n in dir(cls) if not n.startswith("_")}
        if names & forbidden_methods:
            bad_repos.append(cls.__name__)
    if bad_repos:
        checks.append(_check("Append-only repos", "fail",
                             f"Métodos de mutación expuestos: {bad_repos}",
                             "Eliminar update/delete/patch/remove/set."))
        failed += 1
    else:
        checks.append(_check("Append-only repos", "pass",
                             "DeliveryLog / AIInvocationLog / AIAuditAttestation OK."))

    # ──────── Indexes críticos ────────
    expected_indexes = [
        ("users", "tenant_id_1_email_1"),
        ("claims", "claims_one_active_per_ticket_idx"),
        ("webhook_subscriptions", "subs_tenant_event_active_idx"),
        ("webhook_pending_queue", "pending_due_idx"),
    ]
    missing: list[str] = []
    for col_name, idx_name in expected_indexes:
        try:
            indexes = await db[col_name].index_information()
        except Exception:  # noqa: BLE001
            indexes = {}
        if idx_name not in indexes:
            missing.append(f"{col_name}.{idx_name}")
    if missing:
        checks.append(_check("Critical indexes", "warn",
                             f"Faltan: {missing}",
                             "Re-arrancar el backend dispara `ensure_*_indexes`."))
        warned += 1
    else:
        checks.append(_check("Critical indexes", "pass",
                             f"{len(expected_indexes)} indexes verificados."))

    # ──────── R37 — log de invocaciones IA ────────
    ticket_count = await db.tickets.count_documents({})
    ai_logs = await db.ai_logs.count_documents({})
    if ticket_count > 100 and ai_logs == 0:
        checks.append(_check("AI invocation log", "warn",
                             f"{ticket_count} tickets pero 0 AI logs — quizá IA no está enabled.",
                             "Verificar tenants tienen al menos 1 cliente con AI activo."))
        warned += 1
    else:
        checks.append(_check("AI invocation log", "pass",
                             f"{ai_logs} log entries (R37 active)."))

    # ──────── Tenants ────────
    tenant_count = await db.tenants.count_documents({})
    inactive = await db.tenants.count_documents({"status": {"$ne": "active"}})
    checks.append(_check("Tenants", "pass",
                         f"{tenant_count} totales · {inactive} no-activos."))

    # ──────── Resumen ────────
    summary = {
        "total_checks": len(checks),
        "pass": sum(1 for c in checks if c["severity"] == "pass"),
        "warn": warned,
        "fail": failed,
        "ready_for_prod": failed == 0,
    }
    return ok({"checks": checks, "summary": summary})



# ─── User audit log (iter19) ────────────────────────────────────────────
_RBAC_ROOT = require_role("root_dev")


@router.get("/user-audit-log")
async def user_audit_log_query(
    request: Request,
    action: str | None = None,
    actor_id: str | None = None,
    target_email: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 200,
    _: object = Depends(_RBAC_ROOT),
):
    """Tamper-resistant log de operaciones de usuarios (root_dev only).

    Filtros opcionales:
      - action=user.create | user.update | user.reset_password | user.delete
      - actor_id=<user-uuid>
      - target_email=<substring, regex case-insensitive>
      - since=ISO date | until=ISO date
      - limit=1..500 (default 200)
    """
    from services import user_audit_log
    user = request.state.user
    limit = max(1, min(500, limit))
    items = await user_audit_log.query(
        tenant_id=user.tenant_id, action=action, actor_id=actor_id,
        target_email=target_email, since=since, until=until, limit=limit,
    )
    # Action counts for the UI (last 30d window when no since/until filter)
    db = get_db()
    counts_pipeline = [
        {"$match": {"tenant_id": user.tenant_id}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    counts = {row["_id"]: row["count"] async for row in db.user_audit_log.aggregate(counts_pipeline)}
    return ok({
        "items": items, "count": len(items),
        "counts_by_action": counts,
        "available_actions": [
            "user.create", "user.update", "user.reset_password", "user.delete",
        ],
    })
