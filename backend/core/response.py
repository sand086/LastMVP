"""Standard JSON response envelope — MYEXCELLENCE.md sec 7.1 + R10.

EVERY API response — without exception — uses this envelope, even single-field ones.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi.responses import JSONResponse

from .errors import ErrorCode, HTTP_STATUS


def _request_id() -> str:
    return "req_" + secrets.token_hex(6)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ok(
    data: Any = None,
    *,
    pagination: dict | None = None,
    request_id: str | None = None,
    status_code: int = 200,
) -> JSONResponse:
    meta: dict[str, Any] = {
        "request_id": request_id or _request_id(),
        "timestamp": _now_iso(),
    }
    if pagination is not None:
        meta["pagination"] = pagination
    payload = {
        "success": True,
        "data": data,
        "meta": meta,
        "errors": [],
    }
    return JSONResponse(status_code=status_code, content=payload)


def fail(
    code: str,
    message: str,
    *,
    field: str | None = None,
    extra_errors: Iterable[dict] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    errors: list[dict] = [{"code": code, "message": message, "field": field}]
    if extra_errors:
        errors.extend(extra_errors)
    payload = {
        "success": False,
        "data": None,
        "meta": {
            "request_id": request_id or _request_id(),
            "timestamp": _now_iso(),
        },
        "errors": errors,
    }
    status = HTTP_STATUS.get(code, 500)
    return JSONResponse(status_code=status, content=payload)


def validation_failed(field: str, message: str) -> JSONResponse:
    return fail(ErrorCode.VALIDATION_FAILED, message, field=field)
