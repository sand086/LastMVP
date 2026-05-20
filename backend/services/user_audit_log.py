"""User audit log — append-only record of every user-management operation.

Why a dedicated collection?
- `timeline_events` is per-ticket; we need a tenant-wide audit channel.
- Read-only consumers (root_dev, compliance) need fast queries by action /
  date / actor / target without scanning ticket events.
- Append-only contract (no PATCH/DELETE) is enforced at the repo layer to
  guarantee tamper-resistance for compliance audits.

Schema:
  id            uuid
  tenant_id     uuid (scope)
  actor_id      uuid    (who did it)
  actor_email   str
  actor_role    str
  action        str     (user.create | user.update | user.reset_password | user.delete)
  target_id     uuid    (the affected user)
  target_email  str
  before        dict?   (state pre-mutation; null for create)
  after         dict?   (state post-mutation; null for delete)
  ip            str?
  user_agent    str?
  created_at    iso str
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.db import get_db
from core.uuid import new_id


_SAFE_FIELDS = {"email", "name", "role", "status", "client_id"}


def _sanitize(state: Optional[dict]) -> Optional[dict]:
    """Strip secrets (password_hash etc) so audit entries can be displayed."""
    if state is None:
        return None
    return {k: state.get(k) for k in _SAFE_FIELDS if k in state}


async def record(
    *, tenant_id: str, actor_id: str, actor_email: str, actor_role: str,
    action: str, target_id: str, target_email: str,
    before: Optional[dict] = None, after: Optional[dict] = None,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> None:
    """Append a single audit entry. Best-effort: never raises (audit failure
    must NOT block the operation it's auditing)."""
    try:
        await get_db().user_audit_log.insert_one({
            "id": new_id(),
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_email": actor_email,
            "actor_role": actor_role,
            "action": action,
            "target_id": target_id,
            "target_email": target_email,
            "before": _sanitize(before),
            "after": _sanitize(after),
            "ip": ip,
            "user_agent": (user_agent or "")[:200] or None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:  # noqa: BLE001
        # Audit failures are non-fatal. Optionally surface to logger.
        pass


async def query(
    *, tenant_id: str, action: Optional[str] = None,
    actor_id: Optional[str] = None, target_email: Optional[str] = None,
    since: Optional[str] = None, until: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    db = get_db()
    q: dict = {"tenant_id": tenant_id}
    if action:
        q["action"] = action
    if actor_id:
        q["actor_id"] = actor_id
    if target_email:
        q["target_email"] = {"$regex": target_email.lower(), "$options": "i"}
    if since or until:
        date_q: dict = {}
        if since:
            date_q["$gte"] = since
        if until:
            date_q["$lte"] = until
        q["created_at"] = date_q
    cursor = db.user_audit_log.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)
