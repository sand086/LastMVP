"""
Client config service (R00B / SEL01).

Manages per-client configuration for the Routal route-selection module:
  - max_daily_audits
  - selection_enabled
  - scheduler_time (HH:MM, tz America/Mexico_City)
  - active flag

The client_config collection is independent of client_integrations:
  - client_integrations stores credentials and integration type.
  - client_config stores audit/selection policy parameters.

Always queried by `client_id` (multi-tenant isolation).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Defaults applied when creating a new client_config doc
DEFAULTS = {
    "max_daily_audits": 30,
    "selection_enabled": False,  # OFF by default → non-breaking
    "scheduler_time": "06:00",  # Legacy single time
    "scheduler_times": ["06:00"],  # RT-11 multiple cutoffs
    "active": True,
}

VALID_TIME_FORMAT = "%H:%M"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_time(value: str) -> str:
    """Ensure HH:MM in 24h format. Raises ValueError if invalid."""
    try:
        datetime.strptime(value, VALID_TIME_FORMAT)
    except (ValueError, TypeError) as e:
        raise ValueError(f"scheduler_time must be HH:MM (24h), got '{value}'") from e
    return value


def _validate_times(values: list) -> list:
    """Validate and dedupe a list of HH:MM strings."""
    if not isinstance(values, list):
        raise ValueError("scheduler_times must be a list of HH:MM strings")
    if len(values) == 0:
        raise ValueError("scheduler_times must have at least one entry")
    if len(values) > 10:
        raise ValueError("scheduler_times max 10 entries")
    cleaned = sorted({_validate_time(v) for v in values})
    return cleaned


class ClientConfigService:
    """CRUD + bootstrap for client_config docs."""

    def __init__(self, db):
        self.db = db
        self.col = db.client_config

    # ─────────────── READ ───────────────

    async def get(self, client_id: str) -> Optional[dict]:
        return await self.col.find_one({"client_id": client_id}, {"_id": 0})

    async def list_enabled(self) -> list:
        """All clients with selection_enabled=True AND active=True (used by scheduler)."""
        cursor = self.col.find(
            {"selection_enabled": True, "active": True},
            {"_id": 0},
        )
        return [doc async for doc in cursor]

    # ─────────────── WRITE ───────────────

    async def upsert(
        self,
        client_id: str,
        client_name: str,
        max_daily_audits: Optional[int] = None,
        selection_enabled: Optional[bool] = None,
        scheduler_time: Optional[str] = None,
        scheduler_times: Optional[list] = None,
        active: Optional[bool] = None,
    ) -> dict:
        """Create or update. Validates fields and returns the updated doc."""
        existing = await self.get(client_id) or {}

        update = {"client_id": client_id, "client_name": client_name, "updated_at": _now_iso()}

        if max_daily_audits is not None:
            if not isinstance(max_daily_audits, int) or max_daily_audits <= 0 or max_daily_audits > 500:
                raise ValueError("max_daily_audits must be int in range (0, 500]")
            update["max_daily_audits"] = max_daily_audits
        elif "max_daily_audits" not in existing:
            update["max_daily_audits"] = DEFAULTS["max_daily_audits"]

        if selection_enabled is not None:
            update["selection_enabled"] = bool(selection_enabled)
        elif "selection_enabled" not in existing:
            update["selection_enabled"] = DEFAULTS["selection_enabled"]

        # RT-11: scheduler_times (array) takes precedence over scheduler_time (legacy single)
        if scheduler_times is not None:
            update["scheduler_times"] = _validate_times(scheduler_times)
            update["scheduler_time"] = update["scheduler_times"][0]  # back-compat single
        elif scheduler_time is not None:
            update["scheduler_time"] = _validate_time(scheduler_time)
            update["scheduler_times"] = [update["scheduler_time"]]
        else:
            if "scheduler_time" not in existing:
                update["scheduler_time"] = DEFAULTS["scheduler_time"]
            if "scheduler_times" not in existing:
                update["scheduler_times"] = DEFAULTS["scheduler_times"]

        if active is not None:
            update["active"] = bool(active)
        elif "active" not in existing:
            update["active"] = DEFAULTS["active"]

        if not existing:
            update["created_at"] = _now_iso()

        await self.col.update_one(
            {"client_id": client_id},
            {"$set": update},
            upsert=True,
        )
        return await self.get(client_id)

    async def mark_scheduled_run(self, client_id: str, run_date: str) -> None:
        """Records last successful scheduler tick for idempotent daily execution.
        run_date: 'YYYY-MM-DD' in CDMX local time.
        """
        await self.col.update_one(
            {"client_id": client_id},
            {"$set": {"last_scheduled_run_date": run_date, "last_scheduled_run_at": _now_iso()}},
        )


# ─────────────── BOOTSTRAP ───────────────

async def bootstrap_default_clients(db) -> None:
    """Insert a default client_config for Cubbo if it does not exist.

    Called once at startup. Looks up Cubbo by exact name match in `clients`.
    No-op if already configured (idempotent).
    """
    cubbo = await db.clients.find_one({"name": "Cubbo"}, {"_id": 0, "id": 1, "name": 1})
    if not cubbo or not cubbo.get("id"):
        logger.info("[client_config] Cubbo not found in clients collection — skipping bootstrap")
        return

    svc = ClientConfigService(db)
    existing = await svc.get(cubbo["id"])
    if existing:
        return

    await svc.upsert(
        client_id=cubbo["id"],
        client_name=cubbo["name"],
        max_daily_audits=30,
        selection_enabled=True,
        scheduler_time="06:00",
        active=True,
    )
    logger.info(f"[client_config] Bootstrapped Cubbo (client_id={cubbo['id']}) max_daily=30 selection_enabled=True")
