"""Initial schema bootstrap — Mongo equivalent of MIGRATIONS/0001_initial_schema.sql.

Creates the 21 collections listed in PROMPT_01 P0.2 and creates the indexes
required by sec 4.2 of MYEXCELLENCE.md.

Idempotent: safe to run on every boot.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.logger import log
from core.security import hash_password
from core.uuid import new_id
from core.config import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    SUPERADMIN_EMAIL,
    SUPERADMIN_PASSWORD,
)

# PROMPT 08-10 — operational personas seeded for end-to-end validation.
# All share the same default password ``Admin123!`` to keep onboarding short;
# rotate them in production via /api/admin/users (PROMPT_12).
EXTRA_SEED_USERS = [
    {"email": "admin@myexcellence.local",       "name": "Admin Demo",       "role": "admin"},
    {"email": "coord@myexcellence.local",       "name": "Coordinator Demo", "role": "coordinator"},
    {"email": "supervisor@myexcellence.local",  "name": "Supervisor Demo",  "role": "supervisor"},
    {"email": "agent@myexcellence.local",       "name": "Agente Demo",      "role": "agent"},
    # PROMPT_27 — read-only audit persona for AI external audit panel
    {"email": "auditor@myexcellence.local",     "name": "Client Auditor",   "role": "client_auditor"},
]
EXTRA_SEED_PASSWORD = "Admin123!"

# Sec 4 ERD — order matters only for FK reasoning, Mongo doesn't enforce it.
COLLECTIONS = [
    "tenants",
    "projects",
    "clients",
    "subclients",
    "carriers",
    "users",
    "user_scope",
    "motivos",
    "soluciones",
    "automation_permissions",
    "supplier_workflows",
    "holidays",
    "sla_config",
    "guias",
    "tickets",
    "timeline_events",
    "evidencias",
    "location_pins",
    "carrier_status_catalog",
    "cae_unmapped_codes",
    "cae_audit_log",
    # support
    "login_attempts",
]


async def ensure_collections() -> None:
    db = get_db()
    existing = set(await db.list_collection_names())
    for name in COLLECTIONS:
        if name not in existing:
            await db.create_collection(name)
            log.info("collection_created", extra={"context": {"collection": name}})


async def ensure_indexes() -> None:
    db = get_db()
    # Tenants — slug unique
    await db.tenants.create_index("slug", unique=True)
    await db.tenants.create_index("id", unique=True)
    # Users
    await db.users.create_index("email", unique=True)
    await db.users.create_index([("tenant_id", 1), ("id", 1)])
    # Tenant-aware composites (sec 4.2)
    await db.tickets.create_index([("tenant_id", 1), ("status", 1)])
    await db.tickets.create_index([("tenant_id", 1), ("assigned_agent_id", 1)])
    await db.guias.create_index([("tenant_id", 1), ("tracking_id", 1)], unique=True)
    await db.timeline_events.create_index([("tenant_id", 1), ("ticket_id", 1), ("created_at", 1)])
    await db.cae_audit_log.create_index([("tenant_id", 1), ("created_at", -1)])
    # CAE catalog uniqueness — 14.3
    await db.carrier_status_catalog.create_index(
        [("carrier_id", 1), ("raw_code", 1), ("api_version", 1)], unique=True
    )
    await db.cae_unmapped_codes.create_index(
        [("carrier_id", 1), ("raw_code", 1), ("api_version", 1)], unique=True
    )
    # Login attempts (rate limit / lockout tracking, even though we use in-memory primary)
    await db.login_attempts.create_index("identifier")
    # Bundle H · UserScopeAssignment — multi-cliente para externos
    await db.user_scope_assignments.create_index(
        [("tenant_id", 1), ("user_id", 1), ("client_id", 1)], unique=True,
        name="uix_tenant_user_client",
    )
    await db.user_scope_assignments.create_index(
        [("tenant_id", 1), ("user_id", 1)],
        name="ix_tenant_user",
    )
    # Bundle G · Email Multi-Buzón (iter47)
    await db.email_domains.create_index(
        [("tenant_id", 1), ("domain", 1)], unique=True,
        name="uix_tenant_domain",
    )
    await db.email_domains.create_index("verification_status",
                                        name="ix_dom_status")
    await db.email_mailboxes.create_index([("tenant_id", 1)], name="ix_mb_tenant")
    await db.email_mailboxes.create_index(
        [("tenant_id", 1), ("client_id", 1)], name="ix_mb_tenant_client")
    await db.email_mailboxes.create_index([("domain_id", 1)], name="ix_mb_domain")
    await db.email_routing.create_index(
        [("tenant_id", 1), ("workflow_type", 1), ("client_id", 1),
         ("motivo_id", 1), ("priority", -1)],
        name="ix_routing_match",
    )
    await db.email_routing.create_index([("mailbox_id", 1)], name="ix_routing_mb")
    await db.email_send_log.create_index(
        [("tenant_id", 1), ("sent_at", -1)], name="ix_log_tenant_ts")
    await db.email_send_log.create_index([("mailbox_id", 1)], name="ix_log_mb")
    await db.email_send_log.create_index(
        "provider_message_id", name="ix_log_provider_msg", sparse=True)
    log.info("indexes_ensured")


async def seed_root_tenant_and_admin() -> dict:
    """Idempotent seed of:
       * 1 root tenant 'myexcellence'
       * 1 root_dev user (ADMIN_EMAIL)
       * 1 superadmin user (SUPERADMIN_EMAIL)
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    tenant = await db.tenants.find_one({"slug": "myexcellence"})
    if not tenant:
        tenant_doc = {
            "id": new_id(),
            "name": "MyExcellence (root)",
            "slug": "myexcellence",
            "status": "active",
            "created_at": now,
        }
        await db.tenants.insert_one(tenant_doc)
        tenant_doc.pop("_id", None)
        tenant = tenant_doc
        log.info("seed_tenant_created", extra={"context": {"slug": tenant["slug"]}})

    async def _ensure_user(email: str, password: str, role: str, name: str) -> None:
        existing = await db.users.find_one({"email": email.lower()})
        if existing is None:
            await db.users.insert_one({
                "id": new_id(),
                "tenant_id": tenant["id"],
                "email": email.lower(),
                "password_hash": hash_password(password),
                "name": name,
                "role": role,
                "status": "active",
                "last_login_at": None,
                "created_at": now,
            })
            log.info("seed_user_created", extra={"context": {"email": email, "role": role}})
        else:
            # Re-sync password if env changed (matches auth playbook idempotency)
            from core.security import verify_password as _verify
            if not _verify(password, existing["password_hash"]):
                await db.users.update_one(
                    {"id": existing["id"]},
                    {"$set": {"password_hash": hash_password(password), "role": role,
                              "status": "active"}},
                )
                log.info("seed_user_resynced", extra={"context": {"email": email}})

    await _ensure_user(ADMIN_EMAIL, ADMIN_PASSWORD, "root_dev", "Root Dev")
    await _ensure_user(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD, "superadmin", "Superadmin")
    for u in EXTRA_SEED_USERS:
        await _ensure_user(u["email"], EXTRA_SEED_PASSWORD, u["role"], u["name"])

    return tenant


async def run() -> None:
    await ensure_collections()
    await ensure_indexes()
    await seed_root_tenant_and_admin()
    log.info("schema_bootstrap_complete")
