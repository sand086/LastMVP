"""Bundle A · FIX-A3 — Per-tenant whitelist of test domains.

Hardcoded globals (allowed for every tenant) PLUS additional domains a
superadmin / root_dev can register per tenant. The Notifications "Send
test" endpoint consults this whitelist to warn the operator before mailing
an external recipient (e.g. a real client) with un-rendered placeholders.

Schema (collection ``tenant_test_domains``):
    id            uuid
    tenant_id     uuid
    domain        str   (lowercased, no @, e.g. "socio-comercial.com")
    created_by    uuid
    created_at    iso str

Unique index: (tenant_id, domain).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.db import get_db
from core.errors import ErrorCode
from core.response import fail, ok
from core.uuid import new_id
from middleware.rbac import require_min_role

# Hardcoded global whitelist — applies to every tenant.
GLOBAL_TEST_DOMAINS = (
    "my-mensajeria.com",
    "thinkme.com.mx",
    "test",
    "example.com",
    "localhost",
)

router = APIRouter(prefix="/api/admin/test-domains", tags=["admin-notifications"])
_RBAC = require_min_role("admin")


class TestDomainCreate(BaseModel):
    domain: str = Field(min_length=2, max_length=255)


def _normalize(domain: str) -> str:
    return domain.strip().lower().lstrip("@")


async def list_tenant_domains(tenant_id: str) -> list[str]:
    db = get_db()
    cursor = db.tenant_test_domains.find(
        {"tenant_id": tenant_id}, {"_id": 0, "domain": 1},
    )
    return [d["domain"] async for d in cursor]


async def is_whitelisted(domain: str, tenant_id: str) -> bool:
    normalized = _normalize(domain)
    if normalized in GLOBAL_TEST_DOMAINS:
        return True
    tenant_domains = await list_tenant_domains(tenant_id)
    return normalized in tenant_domains


def extract_domain(email: str) -> Optional[str]:
    """Extract domain part from an email-like string. Returns None if malformed."""
    if "@" not in email:
        return None
    parts = email.rsplit("@", 1)
    if len(parts) != 2 or not parts[1]:
        return None
    return parts[1].strip().lower()


@router.get("")
async def list_domains(request: Request, _: object = Depends(_RBAC)):
    """Return hardcoded globals + tenant-specific entries."""
    user = request.state.user
    db = get_db()
    cursor = db.tenant_test_domains.find(
        {"tenant_id": user.tenant_id}, {"_id": 0},
    ).sort("created_at", -1)
    tenant_items = await cursor.to_list(length=200)
    return ok({
        "global_domains": list(GLOBAL_TEST_DOMAINS),
        "tenant_domains": tenant_items,
    })


@router.post("")
async def add_domain(body: TestDomainCreate, request: Request,
                     _: object = Depends(_RBAC)):
    user = request.state.user
    domain = _normalize(body.domain)
    if not domain or "@" in domain or "/" in domain:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Dominio inválido (sin @, sin /).", field="domain")
    if domain in GLOBAL_TEST_DOMAINS:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Este dominio ya está en la whitelist global.",
                    field="domain")
    db = get_db()
    existing = await db.tenant_test_domains.find_one(
        {"tenant_id": user.tenant_id, "domain": domain}, {"_id": 0, "id": 1},
    )
    if existing:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Ya existe ese dominio para este tenant.", field="domain")
    doc = {
        "id": new_id(),
        "tenant_id": user.tenant_id,
        "domain": domain,
        "created_by": user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.tenant_test_domains.insert_one(doc)
    doc.pop("_id", None)
    return ok({"domain": doc})


@router.delete("/{domain_id}")
async def remove_domain(domain_id: str, request: Request,
                        _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    result = await db.tenant_test_domains.delete_one(
        {"id": domain_id, "tenant_id": user.tenant_id},
    )
    if result.deleted_count == 0:
        return fail(ErrorCode.RESOURCE_NOT_FOUND, "Dominio no encontrado.",
                    field="domain_id")
    return ok({"deleted": True})
