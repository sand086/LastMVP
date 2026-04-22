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
"""
import os
import time
import logging
from typing import Any, Dict, Optional

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
}

VALID_BOUNDS = {
    "model": list(MODEL_MAP.keys()),
    "timeout_per_guia": (30, 180),
    "max_routes_concurrent": (1, 5),
    "batch_size_per_route": (1, 10),
    "max_retries": (0, 5),
}

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
    return out


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
    from datetime import datetime, timezone
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
