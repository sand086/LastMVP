"""Audit export con firma HMAC SHA-256 (P2 · PROMPT 26).

Genera un CSV de `ai_invocation_log` filtrado por rango de fechas para
auditoría externa. El CSV se firma con HMAC SHA-256 sobre el body completo
y la firma se devuelve en el header `X-MyE-Audit-Signature`.

Auditores externos verifican: hmac.new(secret, csv_body, sha256).hexdigest()

Secret: env `AUDIT_SIGNING_SECRET`. Debe venir de `.env`; no hay fallback.

Columnas exportadas (orden estable — los auditores consumen este orden):
  invocation_id, created_at, tenant_id, client_id, user_id, feature_code,
  ticket_id, provider, model, status, input_tokens, output_tokens, cost_usd,
  cost_mxn, latency_ms, prompt_hash, response_hash, pii_detected,
  pii_token_count, from_cache, destinatario, approved_at, approved_by,
  webhook_delivered, webhook_status_code, error_code, request_id
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import io
import os
from datetime import datetime, timezone

from core.db import get_db


_AUDIT_COLUMNS = [
    "invocation_id", "created_at", "tenant_id", "client_id", "user_id",
    "feature_code", "ticket_id", "provider", "model", "status",
    "input_tokens", "output_tokens", "cost_usd", "cost_mxn", "latency_ms",
    "prompt_hash", "response_hash", "pii_detected", "pii_token_count",
    "from_cache", "destinatario", "approved_at", "approved_by",
    "webhook_delivered", "webhook_status_code", "error_code", "request_id",
]


def _signing_secret() -> bytes:
    s = os.environ["AUDIT_SIGNING_SECRET"]
    if not s:
        raise RuntimeError("AUDIT_SIGNING_SECRET must be set in .env")
    return s.encode("utf-8")


def sign_body(body: bytes) -> str:
    return "sha256=" + hmac.new(_signing_secret(), body, hashlib.sha256).hexdigest()


async def build_csv(
    *, tenant_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    client_id: str | list[str] | None = None,
    feature_code: str | None = None,
    status: str | None = None,
    limit: int = 10000,
) -> tuple[bytes, dict]:
    """Devuelve (csv_bytes, metadata). Metadata incluye {rows, signature, exported_at}.

    Bundle H: `client_id` puede ser str (single) o list[str] (multi-scope auditor).
    """
    db = get_db()
    q: dict = {"tenant_id": tenant_id}
    if date_from:
        q.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        q.setdefault("created_at", {})["$lte"] = date_to
    if client_id:
        q["client_id"] = {"$in": client_id} if isinstance(client_id, list) else client_id
    if feature_code:
        q["feature_code"] = feature_code
    if status:
        q["status"] = status

    cur = db.ai_invocation_log.find(q, {"_id": 0}).sort("created_at", 1).limit(limit)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_AUDIT_COLUMNS)

    rows = 0
    async for doc in cur:
        writer.writerow([
            doc.get("id", ""), doc.get("created_at", ""), doc.get("tenant_id", ""),
            doc.get("client_id", ""), doc.get("user_id") or "",
            doc.get("feature_code", ""), doc.get("ticket_id") or "",
            doc.get("provider", ""), doc.get("model", ""), doc.get("status", ""),
            doc.get("input_tokens", 0), doc.get("output_tokens", 0),
            doc.get("cost_usd", 0), doc.get("cost_mxn", 0),
            doc.get("latency_ms", 0),
            doc.get("prompt_hash", ""), doc.get("response_hash", ""),
            "1" if doc.get("pii_detected") else "0",
            doc.get("pii_token_count", 0),
            "1" if doc.get("from_cache") else "0",
            doc.get("destinatario") or "",
            doc.get("approved_at") or "", doc.get("approved_by") or "",
            "1" if doc.get("webhook_delivered") else
                ("0" if doc.get("webhook_delivered") is False else ""),
            doc.get("webhook_status_code") or "",
            doc.get("error_code") or "", doc.get("request_id", ""),
        ])
        rows += 1

    body = buf.getvalue().encode("utf-8")
    signature = sign_body(body)
    meta = {
        "rows": rows,
        "signature": signature,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "date_from": date_from, "date_to": date_to,
            "client_id": client_id, "feature_code": feature_code,
            "status": status, "limit": limit,
        },
        "columns": _AUDIT_COLUMNS,
    }
    return body, meta
