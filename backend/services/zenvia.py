"""Zenvia WhatsApp adapter (PROMPT 21).

Adapter único que encapsula:
  - send_text(to, text)
  - send_template(to, template_name, lang, vars)
  - verify_signature(raw_body, signature_header)  # HMAC SHA-256
  - parse_inbound(payload)                         # normaliza al modelo MyE

Reglas:
  - NO logueamos PII: numerOS de teléfono se hash-ean en el log
  - Reintentos exponenciales (3) sobre 5xx y timeouts
  - Rate-limit local 20 req/s (cumplimiento Zenvia)
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import os
import time
from collections import deque
from datetime import datetime, timezone

import httpx

from core.logger import log

_BASE_URL = os.environ["ZENVIA_BASE_URL"]
_TIMEOUT_S = float(os.environ["ZENVIA_TIMEOUT_S"])
_RATE_PER_S = int(os.environ["ZENVIA_RATE_PER_S"])
_FROM = os.environ["ZENVIA_FROM_NUMBER"]     # configurar en Zenvia dashboard

_call_history: deque = deque(maxlen=_RATE_PER_S * 2)
_lock = asyncio.Lock()


def _api_key() -> str:
    return os.environ["ZENVIA_API_KEY"]


def _webhook_secret() -> bytes:
    s = os.environ["ZENVIA_WEBHOOK_SECRET"]
    return s.encode("utf-8")


def _hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()[:12]


async def _rate_limit():
    async with _lock:
        now = time.monotonic()
        while _call_history and (now - _call_history[0]) > 1.0:
            _call_history.popleft()
        if len(_call_history) >= _RATE_PER_S:
            await asyncio.sleep(1.0 - (now - _call_history[0]) + 0.01)
        _call_history.append(time.monotonic())


async def _post(path: str, payload: dict, *, retries: int = 3) -> dict:
    headers = {"X-API-TOKEN": _api_key(), "Content-Type": "application/json"}
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            await _rate_limit()
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                r = await client.post(f"{_BASE_URL}{path}", json=payload, headers=headers)
                if 200 <= r.status_code < 300:
                    return r.json()
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    raise ZenviaError(r.status_code, r.text)
                last_err = ZenviaError(r.status_code, r.text)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_err = e
        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
    raise last_err if last_err else ZenviaError(0, "unknown error")


class ZenviaError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body[:300]
        super().__init__(f"Zenvia {status}: {self.body}")


async def send_text(*, to: str, text: str, from_number: str | None = None) -> dict:
    """Envía mensaje de texto WhatsApp. `to` debe estar en E.164 (+...)."""
    if not to.startswith("+"):
        raise ValueError("Recipient must be E.164 (+...)")
    if not text.strip():
        raise ValueError("Empty text")
    payload = {
        "from": from_number or _FROM or "myexcellence-bot",
        "to": to,
        "contents": [{"type": "text", "text": text}],
    }
    if not _api_key():
        log.warning("zenvia_no_api_key", extra={"context": {"to_hash": _hash_phone(to)}})
        return {"id": "mock-" + _hash_phone(to)[:8],
                "status": "MOCKED", "mocked": True,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    res = await _post("/v2/channels/whatsapp/messages", payload)
    log.info("zenvia_sent", extra={"context": {
        "to_hash": _hash_phone(to), "id": res.get("id", "")[:24],
    }})
    return res


async def send_template(*, to: str, template_name: str, language: str = "es",
                        variables: list[str] | None = None) -> dict:
    payload = {
        "from": _FROM or "myexcellence-bot", "to": to,
        "contents": [{
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language, "policy": "deterministic"},
                "parameters": [{"type": "text", "text": v} for v in (variables or [])],
            },
        }],
    }
    if not _api_key():
        return {"id": "mock-tpl-" + _hash_phone(to)[:8], "mocked": True, "status": "MOCKED"}
    return await _post("/v2/channels/whatsapp/messages", payload)


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """HMAC SHA-256 sobre raw body con webhook secret."""
    if not signature_header:
        return False
    expected = hmac.new(_webhook_secret(), raw_body, hashlib.sha256).hexdigest()
    sent = signature_header.replace("sha256=", "").strip()
    return hmac.compare_digest(expected, sent)


def parse_inbound(payload: dict) -> dict:
    """Normaliza un payload entrante de Zenvia al modelo interno MyE.

    Devuelve `{kind, messages: [...], statuses: [...]}` donde:
      - messages = [{provider_id, from, to, text, media_url, media_type, ts}]
      - statuses = [{provider_id, status, ts}]
    """
    out_messages = []
    out_statuses = []
    for m in (payload.get("messages") or []):
        contents = m.get("contents") or []
        text = None
        media_url = None
        media_type = None
        for c in contents:
            if c.get("type") == "text":
                text = c.get("text")
            elif c.get("type") in ("image", "document", "video", "audio"):
                media_url = c.get("url") or c.get("fileUrl")
                media_type = c.get("type")
        out_messages.append({
            "provider_id": m.get("id", ""),
            "from": m.get("from", ""),
            "to": m.get("to", ""),
            "text": text,
            "media_url": media_url,
            "media_type": media_type,
            "ts": m.get("timestamp"),
        })
    for s in (payload.get("message_statuses") or payload.get("messageStatus") or []):
        if isinstance(s, dict):
            out_statuses.append({
                "provider_id": s.get("id", ""),
                "status": s.get("status", "unknown"),
                "ts": s.get("timestamp"),
            })
    return {"messages": out_messages, "statuses": out_statuses}
