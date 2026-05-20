"""P1.1+P1.2 — Circuit breaker por endpoint + alerta proactiva (PROMPT 39 V3).

Algoritmo:
  - Ventana deslizante 1h (configurable via MYE_WEBHOOK_CB_WINDOW_MIN, default 60).
  - Mínimo de muestras: 5 (configurable via MYE_WEBHOOK_CB_MIN_SAMPLES).
  - Threshold de fallos: 30% (configurable via MYE_WEBHOOK_CB_THRESHOLD_PCT).
  - Cooldown al abrir: 5 min (configurable via MYE_WEBHOOK_CB_COOLDOWN_MIN).
  - Estados: CLOSED (normal) → OPEN (saltea entregas, log 'circuit_open') →
    HALF_OPEN (1 intento de prueba, si OK→CLOSED, si falla→OPEN otro cooldown).

Trigger: se ejecuta tras cada delivery log append. Comparte la misma
  ventana 1h del subscription_id.

Side-effect: al abrir, dispara `notify_circuit_open()` que envía email
  al `ops_contact_email` del cliente cartera (fallback admins del tenant).
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.db import get_db
from core.logger import log


# ───────────────────────── Config ─────────────────────────────────────
def _int(env: str, default: int) -> int:
    try:
        return int(os.environ.get(env, default))
    except ValueError:
        return default


CB_WINDOW_MIN = _int("MYE_WEBHOOK_CB_WINDOW_MIN", 60)
CB_MIN_SAMPLES = _int("MYE_WEBHOOK_CB_MIN_SAMPLES", 5)
CB_THRESHOLD_PCT = _int("MYE_WEBHOOK_CB_THRESHOLD_PCT", 30)
CB_COOLDOWN_MIN = _int("MYE_WEBHOOK_CB_COOLDOWN_MIN", 5)

# Estados que cuentan como falla para el circuit breaker
FAILURE_STATUSES = {"failed_temporary", "failed_permanent", "timeout"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ───────────────────────── Métricas ───────────────────────────────────
async def compute_failure_rate(*, tenant_id: str, subscription_id: str,
                                window_min: int = CB_WINDOW_MIN) -> dict:
    """Calcula ratio de fallas en la ventana. Devuelve métricas."""
    db = get_db()
    cutoff = (_now() - timedelta(minutes=window_min)).isoformat()
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "subscription_id": subscription_id,
                    "created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
        }},
    ]
    counts: dict[str, int] = {}
    async for row in db.webhook_delivery_log.aggregate(pipeline):
        counts[row["_id"]] = row["count"]
    total = sum(counts.values())
    failures = sum(counts.get(s, 0) for s in FAILURE_STATUSES)
    rate_pct = (failures / total * 100) if total else 0.0
    return {
        "total_attempts": total,
        "failures": failures,
        "rate_pct": round(rate_pct, 2),
        "by_status": counts,
        "window_min": window_min,
    }


# ───────────────────────── Open/Close ─────────────────────────────────
async def evaluate_and_trip(*, tenant_id: str, subscription_id: str) -> Optional[dict]:
    """Tras cada delivery, evalúa si hay que ABRIR el circuito.

    Devuelve `{tripped: True, metrics: {...}}` si abrió, `None` en caso contrario.
    """
    db = get_db()
    sub = await db.webhook_subscriptions.find_one(
        {"id": subscription_id, "tenant_id": tenant_id},
        {"_id": 0, "is_circuit_open": 1, "circuit_open_until": 1,
         "endpoint_url": 1, "client_id": 1},
    )
    if not sub:
        return None

    # Si ya está abierto y vigente, no re-disparamos
    if sub.get("is_circuit_open") and (sub.get("circuit_open_until") or "") > _now().isoformat():
        return None

    metrics = await compute_failure_rate(
        tenant_id=tenant_id, subscription_id=subscription_id,
    )
    if metrics["total_attempts"] < CB_MIN_SAMPLES:
        return None
    if metrics["rate_pct"] < CB_THRESHOLD_PCT:
        return None

    # ABRIR
    cooldown_until = (_now() + timedelta(minutes=CB_COOLDOWN_MIN)).isoformat()
    await db.webhook_subscriptions.update_one(
        {"id": subscription_id, "tenant_id": tenant_id},
        {"$set": {
            "is_circuit_open": True,
            "circuit_open_until": cooldown_until,
            "circuit_opened_at": _now().isoformat(),
            "circuit_opened_metrics": metrics,
        }},
    )
    log.warning("webhook_circuit_opened", extra={"context": {
        "tenant_id": tenant_id, "subscription_id": subscription_id,
        "endpoint_url_preview": (sub.get("endpoint_url") or "")[:60],
        "metrics": metrics, "cooldown_until": cooldown_until,
    }})
    # P1.2 — alerta proactiva
    try:
        await _notify_circuit_open(
            tenant_id=tenant_id, subscription=sub,
            metrics=metrics, cooldown_until=cooldown_until,
        )
    except Exception:  # noqa: BLE001
        log.exception("webhook_circuit_alert_failed",
                      extra={"context": {"subscription_id": subscription_id}})
    return {"tripped": True, "metrics": metrics, "cooldown_until": cooldown_until}


async def reset_after_success(*, tenant_id: str, subscription_id: str) -> Optional[dict]:
    """Se llama tras un `delivered` exitoso. Si el circuito estaba abierto y la
    ventana de cooldown ya venció, marcamos como CLOSED. Equivale a HALF_OPEN
    → CLOSED tras la sonda exitosa.
    """
    db = get_db()
    sub = await db.webhook_subscriptions.find_one(
        {"id": subscription_id, "tenant_id": tenant_id},
        {"_id": 0, "is_circuit_open": 1, "circuit_open_until": 1},
    )
    if not sub or not sub.get("is_circuit_open"):
        return None
    # Si el cooldown ya venció, podemos cerrar
    until = sub.get("circuit_open_until") or ""
    if until and until > _now().isoformat():
        # cooldown vigente, no cerramos todavía
        return None
    await db.webhook_subscriptions.update_one(
        {"id": subscription_id, "tenant_id": tenant_id},
        {"$set": {
            "is_circuit_open": False,
            "circuit_open_until": None,
            "circuit_closed_at": _now().isoformat(),
        }},
    )
    log.info("webhook_circuit_closed", extra={"context": {
        "tenant_id": tenant_id, "subscription_id": subscription_id,
    }})
    return {"closed": True}


# ───────────────────────── Alerta proactiva (P1.2) ─────────────────────
async def _notify_circuit_open(*, tenant_id: str, subscription: dict,
                                metrics: dict, cooldown_until: str) -> None:
    """Envía email al ops_contact_email del cliente, con fallback al primer
    admin/superadmin del tenant.
    """
    db = get_db()
    client = await db.clients.find_one(
        {"id": subscription["client_id"], "tenant_id": tenant_id},
        {"_id": 0, "ops_contact_email": 1, "name": 1},
    )
    recipient = (client or {}).get("ops_contact_email")
    if not recipient:
        admin = await db.users.find_one(
            {"tenant_id": tenant_id,
             "role": {"$in": ["admin", "superadmin", "root_dev"]},
             "status": "active"},
            {"_id": 0, "email": 1},
            sort=[("role", -1)],
        )
        recipient = (admin or {}).get("email")
    if not recipient:
        log.warning("webhook_circuit_no_recipient", extra={"context": {
            "tenant_id": tenant_id,
            "subscription_id": subscription.get("id"),
        }})
        return

    from services.notification_service import send_email

    cli_name = (client or {}).get("name", "—")
    url_preview = (subscription.get("endpoint_url") or "")
    subject = f"⚠️ Webhook caído · {cli_name} · {url_preview[:50]}"
    by_status_str = ", ".join(f"{k}: {v}" for k, v in metrics["by_status"].items())
    cooldown_disp = cooldown_until.replace("T", " ")[:19] + " UTC"
    html = f"""\
<div style="font-family: -apple-system,BlinkMacSystemFont,sans-serif; padding: 20px; max-width: 600px;">
  <h2 style="color: #C2410C; margin-top: 0;">Circuit breaker abierto</h2>
  <p>El endpoint webhook saliente del cliente <strong>{cli_name}</strong> superó el
  umbral de fallas (>{CB_THRESHOLD_PCT}% en últimas {metrics['window_min']}m).</p>
  <p>Las próximas entregas se pausarán hasta <strong>{cooldown_disp}</strong>
  para evitar saturar al receptor. Tras ese tiempo, MyExcellence intentará
  una sonda; si responde 2xx, el circuito se cierra y reanuda envíos.</p>
  <table style="border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: 12px; background: #f6f6f4; padding: 12px; border-radius: 6px;">
    <tr><td style="padding: 4px 12px; color: #6b6b6b;">Endpoint</td>
        <td style="padding: 4px 12px;">{url_preview}</td></tr>
    <tr><td style="padding: 4px 12px; color: #6b6b6b;">Intentos</td>
        <td style="padding: 4px 12px;">{metrics['total_attempts']}</td></tr>
    <tr><td style="padding: 4px 12px; color: #6b6b6b;">Fallas</td>
        <td style="padding: 4px 12px;">{metrics['failures']} ({metrics['rate_pct']}%)</td></tr>
    <tr><td style="padding: 4px 12px; color: #6b6b6b;">Por status</td>
        <td style="padding: 4px 12px;">{by_status_str}</td></tr>
  </table>
  <p style="color: #6b6b6b; font-size: 12px; margin-top: 24px;">
    Acción sugerida: validar accesibilidad del endpoint, certificado SSL y latencia.
    Para pausar manualmente o rotar el secreto: visita
    <a href="/admin/webhooks">/admin/webhooks</a>.
  </p>
</div>
"""
    text = (
        f"Circuit breaker abierto para webhook de {cli_name}.\n"
        f"Endpoint: {url_preview}\n"
        f"Intentos: {metrics['total_attempts']}, fallas: {metrics['failures']} "
        f"({metrics['rate_pct']}%) en últimas {metrics['window_min']}m.\n"
        f"Reintento programado: {cooldown_disp}.\n"
        f"Detalle: /admin/webhooks"
    )
    res = await send_email(
        to=recipient, subject=subject, html=html, text=text,
        tags={"event": "webhook_circuit_open",
              "subscription_id": subscription.get("id", "")},
    )
    log.info("webhook_circuit_alert_sent", extra={"context": {
        "to": recipient, "ok": res.ok, "mock": res.mock,
        "subscription_id": subscription.get("id"),
    }})


__all__ = [
    "evaluate_and_trip", "reset_after_success", "compute_failure_rate",
    "FAILURE_STATUSES", "CB_WINDOW_MIN", "CB_MIN_SAMPLES",
    "CB_THRESHOLD_PCT", "CB_COOLDOWN_MIN",
]
