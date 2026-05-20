"""P0.13 — Terminal state protection.

Validates that GuiaRepository.update_status() refuses to modify guías with
is_terminal=True (R02 + sec 5.4 of MYEXCELLENCE.md).
"""
from __future__ import annotations
import pytest
import pytest_asyncio

from core.db import get_db
from core.uuid import new_id
from repositories.guias import GuiaRepository


@pytest_asyncio.fixture
async def terminal_guia(two_tenants):
    db = get_db()
    a = two_tenants["a"]
    gid = new_id()
    await db.guias.insert_one({
        "id": gid, "tenant_id": a, "tracking_id": "TGUI-1",
        "carrier_id": "fedex", "client_id": "c1",
        "carrier_status": "delivered", "internal_status": "delivered",
        "is_terminal": True,
    })
    return {"tenant_id": a, "id": gid}


@pytest.mark.asyncio
async def test_update_status_rejects_terminal(terminal_guia):
    repo = GuiaRepository(tenant_id=terminal_guia["tenant_id"])
    ok = await repo.update_status(
        terminal_guia["id"],
        new_carrier_status="in_transit_again",
        new_internal_status="in_transit",
    )
    assert ok is False  # silently rejected, no exception
    # And the row must be untouched
    db = get_db()
    row = await db.guias.find_one({"id": terminal_guia["id"]})
    assert row["carrier_status"] == "delivered"
    assert row["internal_status"] == "delivered"
    assert row["is_terminal"] is True


@pytest.mark.asyncio
async def test_update_status_promotes_to_terminal(two_tenants):
    """Going from in_transit → delivered must flip is_terminal."""
    db = get_db()
    a = two_tenants["a"]
    gid = new_id()
    await db.guias.insert_one({
        "id": gid, "tenant_id": a, "tracking_id": "TGUI-2",
        "carrier_id": "fedex", "client_id": "c1",
        "carrier_status": "out_for_delivery", "internal_status": "in_transit",
        "is_terminal": False,
    })
    repo = GuiaRepository(tenant_id=a)
    changed = await repo.update_status(
        gid,
        new_carrier_status="DL",
        new_internal_status="delivered",
    )
    assert changed is True
    row = await db.guias.find_one({"id": gid})
    assert row["is_terminal"] is True
