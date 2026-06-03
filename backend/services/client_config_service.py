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

# Defaults applied when creating a new client_config doc.
# 2026-05-30: extended with package-oriented audit cohort (vs. route-count cap).
# Legacy `max_daily_audits` (route count) is preserved as opt-in hard cap.
DEFAULTS = {
    # Legacy (preserved for back-compat; null means no route-count cap)
    "max_daily_audits": 30,
    "selection_enabled": False,  # OFF by default → non-breaking
    "scheduler_time": "06:00",  # Legacy single time
    "scheduler_times": ["06:00"],  # RT-11 multiple cutoffs
    "active": True,
    # ─── Package-oriented audit cohort (RTV2 propuesta 2026-05-30) ───
    "audit_target_packages_daily": 1000,
    "audit_min_packages_daily": 800,
    "audit_max_packages_daily": 1200,
    "audit_target_packages_weekly": 7000,  # calendar Mon–Sun
    "audit_overshoot_tolerance": 0.10,  # 10%
    "audit_distribution_strategy": "adaptive_calendar_week",  # 'flat' | 'adaptive_calendar_week'
    "audit_safety_circuit_breaker": 400,  # max packages 'Evaluando' simultáneos
    # ─── Ingest cutoff (RTV2) ───
    "ingest_cutoff_time": "16:00",  # HH:MM local CDMX
    "ingest_cutoff_timezone": "America/Mexico_City",
    "ingest_eligibility_states": ["in_progress"],
    "ingest_force_resync_at_cutoff": True,
}

VALID_TIME_FORMAT = "%H:%M"
VALID_STRATEGIES = ("flat", "adaptive_calendar_week")
VALID_PLAN_STATES = ("created", "in_progress", "completed", "cancelled")


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


# ─── Validators for package-oriented audit cohort ───
def _validate_int_range(name: str, value, lo: int, hi: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be int")
    if value < lo or value > hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}")
    return value


def _validate_packages_band(target: int, min_p: int, max_p: int) -> None:
    if min_p > target:
        raise ValueError(f"audit_min_packages_daily ({min_p}) cannot exceed target ({target})")
    if target > max_p:
        raise ValueError(f"audit_target_packages_daily ({target}) cannot exceed max ({max_p})")


def _validate_strategy(value: str) -> str:
    if value not in VALID_STRATEGIES:
        raise ValueError(f"audit_distribution_strategy must be one of {VALID_STRATEGIES}")
    return value


def _validate_eligibility_states(values: list) -> list:
    if not isinstance(values, list) or len(values) == 0:
        raise ValueError("ingest_eligibility_states must be a non-empty list")
    invalid = [v for v in values if v not in VALID_PLAN_STATES]
    if invalid:
        raise ValueError(f"ingest_eligibility_states invalid values: {invalid}. Allowed: {VALID_PLAN_STATES}")
    return list(dict.fromkeys(values))  # dedup keep order


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
        # ─── Package-oriented cohort (RTV2 2026-05-30) ───
        audit_target_packages_daily: Optional[int] = None,
        audit_min_packages_daily: Optional[int] = None,
        audit_max_packages_daily: Optional[int] = None,
        audit_target_packages_weekly: Optional[int] = None,
        audit_overshoot_tolerance: Optional[float] = None,
        audit_distribution_strategy: Optional[str] = None,
        audit_safety_circuit_breaker: Optional[int] = None,
        ingest_cutoff_time: Optional[str] = None,
        ingest_cutoff_timezone: Optional[str] = None,
        ingest_eligibility_states: Optional[list] = None,
        ingest_force_resync_at_cutoff: Optional[bool] = None,
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

        # ─── Package-oriented cohort (RTV2) ───
        # Compute final values respecting precedence: explicit param > existing > default.
        def _resolve_int(name, val, lo, hi):
            if val is not None:
                update[name] = _validate_int_range(name, val, lo, hi)
                return update[name]
            return existing.get(name, DEFAULTS[name])

        def _resolve_float(name, val, lo, hi):
            if val is not None:
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    raise ValueError(f"{name} must be number")
                if val < lo or val > hi:
                    raise ValueError(f"{name} must be in [{lo}, {hi}]")
                update[name] = float(val)
                return update[name]
            return existing.get(name, DEFAULTS[name])

        final_target = _resolve_int("audit_target_packages_daily", audit_target_packages_daily, 1, 100000)
        final_min = _resolve_int("audit_min_packages_daily", audit_min_packages_daily, 0, 100000)
        final_max = _resolve_int("audit_max_packages_daily", audit_max_packages_daily, 1, 100000)
        _resolve_int("audit_target_packages_weekly", audit_target_packages_weekly, 1, 1000000)
        _resolve_float("audit_overshoot_tolerance", audit_overshoot_tolerance, 0.0, 1.0)
        _resolve_int("audit_safety_circuit_breaker", audit_safety_circuit_breaker, 1, 100000)

        # Coherence check on the BAND (target ∈ [min, max])
        _validate_packages_band(final_target, final_min, final_max)

        if audit_distribution_strategy is not None:
            update["audit_distribution_strategy"] = _validate_strategy(audit_distribution_strategy)
        elif "audit_distribution_strategy" not in existing:
            update["audit_distribution_strategy"] = DEFAULTS["audit_distribution_strategy"]

        if ingest_cutoff_time is not None:
            update["ingest_cutoff_time"] = _validate_time(ingest_cutoff_time)
        elif "ingest_cutoff_time" not in existing:
            update["ingest_cutoff_time"] = DEFAULTS["ingest_cutoff_time"]

        if ingest_cutoff_timezone is not None:
            # Validate timezone string
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(ingest_cutoff_timezone)
            except Exception as e:
                raise ValueError(f"ingest_cutoff_timezone invalid: {e}")
            update["ingest_cutoff_timezone"] = ingest_cutoff_timezone
        elif "ingest_cutoff_timezone" not in existing:
            update["ingest_cutoff_timezone"] = DEFAULTS["ingest_cutoff_timezone"]

        if ingest_eligibility_states is not None:
            update["ingest_eligibility_states"] = _validate_eligibility_states(ingest_eligibility_states)
        elif "ingest_eligibility_states" not in existing:
            update["ingest_eligibility_states"] = DEFAULTS["ingest_eligibility_states"]

        if ingest_force_resync_at_cutoff is not None:
            update["ingest_force_resync_at_cutoff"] = bool(ingest_force_resync_at_cutoff)
        elif "ingest_force_resync_at_cutoff" not in existing:
            update["ingest_force_resync_at_cutoff"] = DEFAULTS["ingest_force_resync_at_cutoff"]

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
        # RTV2 package-oriented defaults
        audit_target_packages_daily=1000,
        audit_min_packages_daily=800,
        audit_max_packages_daily=1200,
        audit_target_packages_weekly=7000,
        ingest_cutoff_time="16:00",
        ingest_eligibility_states=["in_progress"],
    )
    logger.info(f"[client_config] Bootstrapped Cubbo (client_id={cubbo['id']}) target=1000/day cutoff=16:00")
