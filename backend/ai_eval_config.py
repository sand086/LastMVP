"""
AI Evaluation runtime configuration.
Reads from MongoDB `config` collection key='ai_eval_config', falls back to env vars.
Cached in-memory for 30s to avoid hammering DB on every call.

Configurable keys:
  - model: 'haiku-4-5' (default) | 'sonnet-4-5'
  - timeout_per_guia: seconds (default 60)
  - max_routes_concurrent: 1–5 (default 3)
  - batch_size_per_route: 1–10 (default 5)
  - max_retries: 0–5 (default 3)
  - paused_until: ISO string (UTC) — worker paused until this moment; null=not paused
  - pause_reason: free-text (why it was paused)
  - schedule_enabled: bool — whether schedule_windows are active
  - schedule_windows: list of {name, days:[0-6], from:'HH:MM', to:'HH:MM', tz:'America/Mexico_City'}
"""
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Model ID mapping (internal alias → Anthropic identifier)
MODEL_MAP = {
    "haiku-4-5": "claude-haiku-4-5-20251001",
    "sonnet-4-5": "claude-sonnet-4-5-20250929",
}

DEFAULTS: Dict[str, Any] = {
    "model": os.environ.get("AI_EVAL_MODEL", "haiku-4-5"),
    "timeout_per_guia": int(os.environ.get("AI_EVAL_TIMEOUT_PER_GUIA", "60")),
    "max_routes_concurrent": int(os.environ.get("AI_EVAL_MAX_ROUTES_CONCURRENT", "3")),
    "batch_size_per_route": int(os.environ.get("AI_EVAL_BATCH_SIZE_PER_ROUTE", "5")),
    "max_retries": int(os.environ.get("AI_EVAL_MAX_RETRIES", "3")),
    "paused_until": None,
    "pause_reason": None,
    "schedule_enabled": False,
    "schedule_windows": [],
    # Smart autopause (P09): pausar si shadow_cost_pct excede umbral en ventana reciente
    "shadow_autopause_enabled": True,
    "shadow_threshold_pct": int(os.environ.get("AI_EVAL_SHADOW_THRESHOLD_PCT", "10")),  # 10% default
    "shadow_window_minutes": int(os.environ.get("AI_EVAL_SHADOW_WINDOW_MINUTES", "15")),
    "shadow_min_events": int(os.environ.get("AI_EVAL_SHADOW_MIN_EVENTS", "10")),  # baseline mínimo para evitar trigger con 1-2 fallos
    "shadow_autopause_minutes": int(os.environ.get("AI_EVAL_SHADOW_AUTOPAUSE_MINUTES", "20")),  # cuánto pausar al disparar
}

VALID_BOUNDS = {
    "model": list(MODEL_MAP.keys()),
    "timeout_per_guia": (30, 180),
    "max_routes_concurrent": (1, 5),
    "batch_size_per_route": (1, 10),
    "max_retries": (0, 5),
    "shadow_threshold_pct": (1, 100),
    "shadow_window_minutes": (5, 60),
    "shadow_min_events": (1, 100),
    "shadow_autopause_minutes": (5, 240),
}

DEFAULT_TZ = "America/Mexico_City"
_CACHE_TTL_SECONDS = 30
_cache = {"ts": 0.0, "data": None}


def _validate(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp values to valid bounds and fall back to defaults on invalid entries."""
    out = dict(DEFAULTS)
    if not isinstance(cfg, dict):
        return out
    for key, default in DEFAULTS.items():
        val = cfg.get(key, default)
        bounds = VALID_BOUNDS.get(key)
        if isinstance(bounds, list):
            out[key] = val if val in bounds else default
        elif isinstance(bounds, tuple):
            try:
                v = int(val)
                out[key] = max(bounds[0], min(bounds[1], v))
            except (TypeError, ValueError):
                out[key] = default
        else:
            out[key] = val
    # Normalize bool flag explicitly to avoid truthy strings persisting
    out["shadow_autopause_enabled"] = bool(out.get("shadow_autopause_enabled", True))
    # Normalize schedule_windows
    windows = out.get("schedule_windows") or []
    if not isinstance(windows, list):
        windows = []
    clean_windows = []
    for w in windows[:10]:  # hard cap
        if not isinstance(w, dict):
            continue
        days = [int(d) for d in (w.get("days") or []) if isinstance(d, (int, float)) and 0 <= int(d) <= 6]
        frm = str(w.get("from", "09:00"))[:5]
        to = str(w.get("to", "13:00"))[:5]
        if not _valid_hhmm(frm) or not _valid_hhmm(to):
            continue
        clean_windows.append({
            "name": str(w.get("name", "Ventana"))[:60],
            "days": sorted(set(days)),
            "from": frm,
            "to": to,
            "tz": str(w.get("tz", DEFAULT_TZ))[:40],
        })
    out["schedule_windows"] = clean_windows
    out["schedule_enabled"] = bool(out.get("schedule_enabled", False))
    return out


def _valid_hhmm(s: str) -> bool:
    try:
        h, m = s.split(":")
        h, m = int(h), int(m)
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False


def _in_window(now_utc: datetime, window: dict) -> bool:
    """Check if now_utc falls within a recurring schedule window.
    Day index uses Python's Monday=0..Sunday=6."""
    try:
        tz = ZoneInfo(window.get("tz") or DEFAULT_TZ)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)
    local = now_utc.astimezone(tz)
    days = window.get("days") or []
    if days and local.weekday() not in days:
        return False
    fh, fm = map(int, window["from"].split(":"))
    th, tm = map(int, window["to"].split(":"))
    from_min = fh * 60 + fm
    to_min = th * 60 + tm
    cur_min = local.hour * 60 + local.minute
    # Overnight window handling (e.g., 22:00 → 06:00)
    if from_min <= to_min:
        return from_min <= cur_min < to_min
    return cur_min >= from_min or cur_min < to_min


def is_worker_paused(cfg: Dict[str, Any], now_utc: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
    """Return (is_paused, reason_human_readable)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    # 1) Manual pause
    paused_until = cfg.get("paused_until")
    if paused_until:
        try:
            until = datetime.fromisoformat(paused_until.replace("Z", "+00:00"))
            if until > now_utc:
                delta = until - now_utc
                mins = int(delta.total_seconds() // 60)
                reason = cfg.get("pause_reason") or "Pausa manual"
                return True, f"{reason} · reanuda en {mins} min"
        except (ValueError, AttributeError):
            pass
    # 2) Schedule windows
    if cfg.get("schedule_enabled") and cfg.get("schedule_windows"):
        for w in cfg["schedule_windows"]:
            if _in_window(now_utc, w):
                return True, f"Ventana programada: {w.get('name', 'N/A')} ({w['from']}–{w['to']})"
    return False, None


async def get_ai_eval_config(db, force_refresh: bool = False) -> Dict[str, Any]:
    """Return current AI evaluation config with in-memory caching."""
    now = time.time()
    if not force_refresh and _cache["data"] and (now - _cache["ts"] < _CACHE_TTL_SECONDS):
        return _cache["data"]
    try:
        doc = await db.config.find_one({"key": "ai_eval_config"}, {"_id": 0, "value": 1})
        cfg = _validate((doc or {}).get("value") or {})
    except Exception as e:
        logger.warning(f"ai_eval_config read failed, using defaults: {e}")
        cfg = dict(DEFAULTS)
    _cache["data"] = cfg
    _cache["ts"] = now
    return cfg


async def get_model_identifier(db) -> str:
    """Return the full Anthropic model id (e.g. claude-haiku-4-5-20251001)."""
    cfg = await get_ai_eval_config(db)
    return MODEL_MAP.get(cfg["model"], MODEL_MAP["haiku-4-5"])


def invalidate_cache() -> None:
    _cache["ts"] = 0.0
    _cache["data"] = None


async def set_ai_eval_config(db, patch: Dict[str, Any], user_email: Optional[str] = None) -> Dict[str, Any]:
    """Upsert config document and invalidate cache."""
    current = await get_ai_eval_config(db, force_refresh=True)
    merged = {**current, **{k: v for k, v in patch.items() if k in DEFAULTS}}
    validated = _validate(merged)
    await db.config.update_one(
        {"key": "ai_eval_config"},
        {"$set": {
            "key": "ai_eval_config",
            "value": validated,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user_email,
        }},
        upsert=True,
    )
    invalidate_cache()
    return validated


async def pause_worker(db, duration_minutes: int, reason: Optional[str] = None, user_email: Optional[str] = None) -> Dict[str, Any]:
    """Pause worker for N minutes (kill-switch applied by worker loop)."""
    until = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(duration_minutes)))
    return await set_ai_eval_config(db, {
        "paused_until": until.isoformat(),
        "pause_reason": (reason or "Pausa manual")[:120],
    }, user_email)


async def resume_worker(db, user_email: Optional[str] = None) -> Dict[str, Any]:
    """Clear pause state."""
    return await set_ai_eval_config(db, {
        "paused_until": None,
        "pause_reason": None,
    }, user_email)
