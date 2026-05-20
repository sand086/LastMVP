"""Health endpoint smoke test."""
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport

from server import app


@pytest.mark.asyncio
async def test_health_returns_envelope():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["version"] == "2.1-MVP"
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]
    assert body["errors"] == []
