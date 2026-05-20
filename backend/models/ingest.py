"""Pydantic payloads for ingest endpoints (PROMPT 04)."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class WebhookEvent(BaseModel):
    """Body of POST /api/guias/ingest/webhook?client_id=…"""
    tracking_id: str = Field(min_length=1, max_length=100)
    carrier_code: str = Field(min_length=1, max_length=50)
    carrier_status: str = Field(min_length=1, max_length=100)
    carrier_status_description: Optional[str] = Field(default=None, max_length=500)
    raw_code: Optional[str] = Field(default=None, max_length=100)
    api_version: str = Field(default="v1", max_length=20)
    event_at: Optional[str] = None  # ISO datetime; defaults to server now if omitted
    raw_payload: Optional[dict] = None


class PullRequest(BaseModel):
    """Used by the admin manual-pull trigger.

    Real pulling lands in PROMPT 09 (cron). For now an admin can fire a
    one-shot fetch to test the wiring; the body is empty by design.
    """
    pass
