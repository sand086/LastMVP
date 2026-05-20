"""P0.12 — Multi-tenant isolation test.

Creates 2 ficticious tenants and proves that a repository scoped to tenant A
cannot read, update or delete data belonging to tenant B (R01 + R08).
The test FAILS — by design — if the system ever permits a cross-tenant leak.
"""
from __future__ import annotations
import pytest
import pytest_asyncio

from core.db import get_db
from core.uuid import new_id
from repositories.guias import GuiaRepository


@pytest_asyncio.fixture
async def seeded(two_tenants):
    db = get_db()
    a, b = two_tenants["a"], two_tenants["b"]
    # 1 guía per tenant, identical tracking_id to push the test
    await db.guias.insert_many([
        {"id": new_id(), "tenant_id": a, "tracking_id": "GUI-1",
         "carrier_id": "fedex", "client_id": "c1",
         "carrier_status": "in_transit", "internal_status": "in_transit",
         "is_terminal": False},
        {"id": new_id(), "tenant_id": b, "tracking_id": "GUI-1",
         "carrier_id": "fedex", "client_id": "c1",
         "carrier_status": "in_transit", "internal_status": "in_transit",
         "is_terminal": False},
    ])
    return {"a": a, "b": b}


@pytest.mark.asyncio
async def test_repository_cannot_read_other_tenant(seeded):
    repo_a = GuiaRepository(tenant_id=seeded["a"])
    rows = await repo_a.find({"tracking_id": "GUI-1"})
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == seeded["a"]


@pytest.mark.asyncio
async def test_repository_cannot_update_other_tenant(seeded):
    repo_a = GuiaRepository(tenant_id=seeded["a"])
    # Try to "smuggle" tenant_id from B in the query
    modified = await repo_a.update_one(
        {"tracking_id": "GUI-1", "tenant_id": seeded["b"]},
        {"carrier_status": "tampered"},
    )
    assert modified == 0
    # And confirm B's row is unchanged
    db = get_db()
    b_row = await db.guias.find_one({"tenant_id": seeded["b"], "tracking_id": "GUI-1"})
    assert b_row["carrier_status"] == "in_transit"


@pytest.mark.asyncio
async def test_repository_cannot_delete_other_tenant(seeded):
    repo_a = GuiaRepository(tenant_id=seeded["a"])
    deleted = await repo_a.delete_one({"tracking_id": "GUI-1", "tenant_id": seeded["b"]})
    assert deleted == 0
    db = get_db()
    assert await db.guias.count_documents({"tenant_id": seeded["b"]}) == 1


@pytest.mark.asyncio
async def test_zero_crosses_recorded(seeded):
    """End-to-end recap: after all the attempts above, A and B counts unchanged."""
    db = get_db()
    assert await db.guias.count_documents({"tenant_id": seeded["a"]}) == 1
    assert await db.guias.count_documents({"tenant_id": seeded["b"]}) == 1
