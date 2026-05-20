"""Structured JSON logger with correlation_id — Bootstrap P1.2.

Logs to LOG_PATH (default /var/log/myexcellence/app.log) and stdout.
Each log line is a single JSON object so it can be ingested by Datadog/ELK later.
"""
from __future__ import annotations
import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from .config import LOG_PATH, LOG_LEVEL

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str:
    return _correlation_id.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": _correlation_id.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Support extra={"context": {...}}
        ctx = getattr(record, "context", None)
        if isinstance(ctx, dict):
            payload["context"] = ctx
        return json.dumps(payload, ensure_ascii=False)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("myexcellence")
    if logger.handlers:
        return logger
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)
    formatter = JsonFormatter()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        file_handler = RotatingFileHandler(LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (PermissionError, OSError):
        # Log directory not writable in some environments; stdout is enough.
        pass

    logger.propagate = False
    return logger


log = _build_logger()
