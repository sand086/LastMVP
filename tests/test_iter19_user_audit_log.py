"""Iter19 — User audit log.

Verifica que cada mutación de usuario genera un audit entry y que el
endpoint de query funciona con todos los filtros + RBAC.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="root_dev"):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email=f"{user_id[:6]}@t")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    root_id = new_id()
    super_id = new_id()
    admin_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "audit-iter19",
                                 "name": "T", "status": "active"})
    await db.users.insert_many([
        {"id": root_id, "tenant_id": tid, "email": "root@t", "name": "Root",
         "role": "root_dev", "status": "active"},
        {"id": super_id, "tenant_id": tid, "email": "super@t", "name": "Super",
         "role": "superadmin", "status": "active"},
        {"id": admin_id, "tenant_id": tid, "email": "ad@t", "name": "Admin",
         "role": "admin", "status": "active"},
    ])
    return {"tid": tid, "root": root_id, "super": super_id, "admin": admin_id}


class TestAuditLogMutations:
    async def test_create_emits_audit(self, env, http_client, db):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        await http_client.post("/api/admin/users", headers=h, json={
            "email": "newuser@t.com", "name": "New", "role": "agent",
        })
        log = await db.user_audit_log.find_one(
            {"action": "user.create", "target_email": "newuser@t.com"},
            {"_id": 0},
        )
        assert log is not None
        assert log["actor_id"] == env["root"]
        assert log["before"] is None
        assert log["after"]["email"] == "newuser@t.com"
        assert log["after"]["role"] == "agent"
        # No password_hash en el dump
        assert "password_hash" not in log["after"]

    async def test_update_emits_audit_with_diff(self, env, http_client, db):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        await http_client.patch(f"/api/admin/users/{env['admin']}",
                                 headers=h, json={"name": "Updated"})
        log = await db.user_audit_log.find_one(
            {"action": "user.update", "target_id": env["admin"]},
            {"_id": 0},
        )
        assert log is not None
        assert log["before"]["name"] != log["after"]["name"]

    async def test_reset_password_emits_audit(self, env, http_client, db):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        await http_client.post(
            f"/api/admin/users/{env['admin']}/reset-password", headers=h,
        )
        log = await db.user_audit_log.find_one(
            {"action": "user.reset_password", "target_id": env["admin"]},
            {"_id": 0},
        )
        assert log is not None
        # Nunca registramos la password en el audit
        assert log["after"] is None

    async def test_delete_emits_audit(self, env, http_client, db):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        await http_client.delete(f"/api/admin/users/{env['admin']}", headers=h)
        log = await db.user_audit_log.find_one(
            {"action": "user.delete", "target_id": env["admin"]}, {"_id": 0},
        )
        assert log is not None
        assert log["after"] is None
        assert log["before"]["email"] == "ad@t"


class TestAuditLogQuery:
    async def test_returns_count_by_action(self, env, http_client, db):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        # 2 creates + 1 reset + 1 delete
        await http_client.post("/api/admin/users", headers=h, json={
            "email": "a1@t.com", "name": "A", "role": "agent"})
        await http_client.post("/api/admin/users", headers=h, json={
            "email": "a2@t.com", "name": "A", "role": "agent"})
        await http_client.post(
            f"/api/admin/users/{env['admin']}/reset-password", headers=h)
        await http_client.delete(f"/api/admin/users/{env['admin']}", headers=h)
        r = await http_client.get("/api/admin/security/user-audit-log",
                                   headers=h)
        d = r.json()["data"]
        assert d["count"] == 4
        assert d["counts_by_action"]["user.create"] == 2
        assert d["counts_by_action"]["user.reset_password"] == 1
        assert d["counts_by_action"]["user.delete"] == 1

    async def test_filter_by_action(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        await http_client.post("/api/admin/users", headers=h, json={
            "email": "x@t.com", "name": "X", "role": "agent"})
        await http_client.delete(f"/api/admin/users/{env['admin']}", headers=h)
        r = await http_client.get(
            "/api/admin/security/user-audit-log?action=user.delete", headers=h,
        )
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["action"] == "user.delete"

    async def test_filter_by_target_email(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        await http_client.post("/api/admin/users", headers=h, json={
            "email": "needle@t.com", "name": "N", "role": "agent"})
        await http_client.post("/api/admin/users", headers=h, json={
            "email": "hay@t.com", "name": "H", "role": "agent"})
        r = await http_client.get(
            "/api/admin/security/user-audit-log?target_email=needle",
            headers=h,
        )
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["target_email"] == "needle@t.com"

    async def test_rbac_root_only(self, env, http_client):
        h_super = _bearer(user_id=env["super"], tenant_id=env["tid"],
                           role="superadmin")
        r = await http_client.get("/api/admin/security/user-audit-log",
                                   headers=h_super)
        assert r.status_code == 403
        h_admin = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                           role="admin")
        r = await http_client.get("/api/admin/security/user-audit-log",
                                   headers=h_admin)
        assert r.status_code == 403

    async def test_tenant_isolation(self, env, http_client, db):
        # Insert audit entry from another tenant — should not leak
        other_tid = new_id()
        from datetime import datetime, timezone
        await db.user_audit_log.insert_one({
            "id": new_id(), "tenant_id": other_tid,
            "actor_id": new_id(), "actor_email": "other@t",
            "actor_role": "root_dev", "action": "user.create",
            "target_id": new_id(), "target_email": "leak@t",
            "before": None, "after": {"email": "leak@t"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.get("/api/admin/security/user-audit-log",
                                   headers=h)
        emails = {e["target_email"] for e in r.json()["data"]["items"]}
        assert "leak@t" not in emails
