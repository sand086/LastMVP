"""Tenant-scoped email templates (PROMPT 11 backlog).

Permite a admins de tenant sobre-escribir las plantillas por defecto del
NotificationService con su propio subject/HTML/texto.

Sintaxis de variables:
  {{ ticket_id }}, {{ tracking_id }}, {{ recipient_name }}, {{ message }},
  {{ cta_url }}, {{ cta_label }}, {{ tenant_name }}, {{ now_utc }}

Claves de plantilla soportadas:
  - incident_notice       (PROMPT 13 — notificación al CxC del cliente)
  - test_email            (PROMPT 11 — email de prueba)

Si no existe override por tenant, se usa la default del service hardcoded.
"""
from __future__ import annotations
from datetime import datetime, timezone
import re
from typing import Optional

from core.db import get_db
from core.uuid import new_id


SUPPORTED_KEYS = {
    # Generic legacy
    "incident_notice", "test_email",
    # Iter54 — P0: 8 plantillas por (incident_type × variant)
    "incident_address_issue_contacted",
    "incident_address_issue_no_contact",
    "incident_refused_confirmed",
    "incident_refused_not_confirmed",
    "incident_refused_no_contact",
    "incident_recipient_absent_contacted",
    "incident_recipient_absent_no_contact",
    "final_return_to_origin",
}

# Iter54 — mapeo incident_type → (variant) → template_key
INCIDENT_VARIANT_TEMPLATE: dict[tuple[str, str], str] = {
    ("address_issue", "contacted"):     "incident_address_issue_contacted",
    ("address_issue", "no_contact"):    "incident_address_issue_no_contact",
    ("refused", "confirmed"):           "incident_refused_confirmed",
    ("refused", "not_confirmed"):       "incident_refused_not_confirmed",
    ("refused", "no_contact"):          "incident_refused_no_contact",
    ("recipient_absent", "contacted"):  "incident_recipient_absent_contacted",
    ("recipient_absent", "no_contact"): "incident_recipient_absent_no_contact",
}


def resolve_template_key(incident_type: str | None,
                         variant: str = "no_contact") -> str:
    """Iter54 — Devuelve la `template_key` para (incident_type, variant).

    Fallback: `incident_notice` (template legacy genérico) si no hay match.
    """
    if not incident_type:
        return "incident_notice"
    key = INCIDENT_VARIANT_TEMPLATE.get((incident_type, variant))
    if key:
        return key
    # Si el variant no aplica para este tipo, probamos no_contact y luego legacy
    fallback = INCIDENT_VARIANT_TEMPLATE.get((incident_type, "no_contact"))
    return fallback or "incident_notice"

# Variables expuestas en cada template (UX hint para el editor)
_INCIDENT_VARS = [
    "recipient_name", "ticket_id", "tracking_id", "carrier_name",
    "incidence_label", "operator_name", "client_name",
    "message", "cta_url", "cta_label", "tenant_name", "now_utc",
]
TEMPLATE_VARIABLES = {
    "incident_notice":                          _INCIDENT_VARS,
    "test_email": [
        "recipient_name", "tenant_name", "now_utc",
    ],
    "incident_address_issue_contacted":         _INCIDENT_VARS,
    "incident_address_issue_no_contact":        _INCIDENT_VARS,
    "incident_refused_confirmed":               _INCIDENT_VARS,
    "incident_refused_not_confirmed":           _INCIDENT_VARS,
    "incident_refused_no_contact":              _INCIDENT_VARS,
    "incident_recipient_absent_contacted":      _INCIDENT_VARS,
    "incident_recipient_absent_no_contact":     _INCIDENT_VARS,
    "final_return_to_origin":                   _INCIDENT_VARS,
}

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_string(template: str, ctx: dict) -> str:
    """Render minimal `{{var}}` substitution. Missing vars → empty string."""
    def _sub(m: re.Match) -> str:
        key = m.group(1)
        v = ctx.get(key, "")
        return str(v) if v is not None else ""
    return _VAR_RE.sub(_sub, template or "")


async def get_template(*, tenant_id: str, key: str) -> Optional[dict]:
    if key not in SUPPORTED_KEYS:
        return None
    db = get_db()
    doc = await db.email_templates.find_one(
        {"tenant_id": tenant_id, "key": key}, {"_id": 0},
    )
    return doc


async def list_templates(*, tenant_id: str) -> list[dict]:
    db = get_db()
    cursor = db.email_templates.find({"tenant_id": tenant_id}, {"_id": 0}).limit(50)
    return await cursor.to_list(length=50)


async def upsert_template(*, tenant_id: str, key: str, subject: str,
                          html_body: str, text_body: str, updated_by: str) -> dict:
    if key not in SUPPORTED_KEYS:
        raise ValueError(f"Unsupported template key: {key}")
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "tenant_id": tenant_id, "key": key,
        "subject": subject.strip()[:200],
        "html_body": html_body[:20_000],
        "text_body": text_body[:10_000],
        "updated_by": updated_by, "updated_at": now,
    }
    existing = await db.email_templates.find_one(
        {"tenant_id": tenant_id, "key": key}, {"_id": 0, "id": 1, "created_at": 1},
    )
    if existing:
        doc["id"] = existing["id"]
        doc["created_at"] = existing.get("created_at", now)
        await db.email_templates.update_one(
            {"id": existing["id"]}, {"$set": doc},
        )
    else:
        doc["id"] = new_id()
        doc["created_at"] = now
        await db.email_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def delete_template(*, tenant_id: str, key: str) -> int:
    db = get_db()
    r = await db.email_templates.delete_one({"tenant_id": tenant_id, "key": key})
    return r.deleted_count


async def render_for_tenant(*, tenant_id: str, key: str, ctx: dict) -> Optional[dict]:
    """Renderiza el template override del tenant. Devuelve None si no hay override.
    El llamador (notification_service) usa su default si esto devuelve None.
    """
    doc = await get_template(tenant_id=tenant_id, key=key)
    if not doc:
        return None
    base_ctx = {
        "now_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        **ctx,
    }
    return {
        "subject": render_string(doc["subject"], base_ctx),
        "html": render_string(doc["html_body"], base_ctx),
        "text": render_string(doc["text_body"], base_ctx),
    }
