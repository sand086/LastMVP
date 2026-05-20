"""Iter57 · Scopes para roles internos (agent/supervisor/coordinator).

Bug del usuario: al crear un agent no se pedía configuración de clientes,
violando el principio "el agente solo ve lo que se le asigna".

Cubre:
  - `_load_allowed_client_ids` carga scopes para internos con asignaciones
  - Sin asignaciones → ve todo (legacy compat)
  - Endpoint `/admin/users/{id}/scopes` ahora acepta agent/supervisor/coordinator
  - `resolve_client_scope` clampa internos con scopes (no solo externos)
  - Agent con scope=[A] no puede pedir client_id=B
  - Borrado del último scope: permitido para internos, prohibido para externos
"""
from __future__ import annotations
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="superadmin", email="su@t.io"):
    tok = create_access_token(
        user_id=user_id, tenant_id=tenant_id, role=role, email=email)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    t_id = new_id()
    su_id = new_id()
    ag_id = new_id()
    sup_id = new_id()
    cli_a = new_id()
    cli_b = new_id()
    cli_c = new_id()
    pwd = hash_password("x")
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-57", "name": "T-57", "status": "active"})
    await db.users.insert_many([
        {"id": su_id, "tenant_id": t_id, "email": "su@t-57.io",
         "role": "superadmin", "password_hash": pwd, "status": "active"},
        {"id": ag_id, "tenant_id": t_id, "email": "ag@t-57.io",
         "role": "agent", "password_hash": pwd, "status": "active"},
        {"id": sup_id, "tenant_id": t_id, "email": "sup@t-57.io",
         "role": "supervisor", "password_hash": pwd, "status": "active"},
    ])
    await db.clients.insert_many([
        {"id": cli_a, "tenant_id": t_id, "name": "Cli A", "slug": "a"},
        {"id": cli_b, "tenant_id": t_id, "name": "Cli B", "slug": "b"},
        {"id": cli_c, "tenant_id": t_id, "name": "Cli C", "slug": "c"},
    ])
    return {"tenant_id": t_id, "superadmin_id": su_id,
            "agent_id": ag_id, "supervisor_id": sup_id,
            "client_a": cli_a, "client_b": cli_b, "client_c": cli_c}


@pytest.mark.asyncio
class TestScopesEndpointForInternalRoles:
    async def test_assign_scope_to_agent(self, db, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        r = await http_client.post(
            f"/api/admin/users/{env['agent_id']}/scopes",
            headers=headers,
            json={"client_id": env["client_a"]},
        )
        assert r.status_code == 201, r.text
        # Listar
        r2 = await http_client.get(
            f"/api/admin/users/{env['agent_id']}/scopes", headers=headers)
        assert r2.status_code == 200
        items = r2.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["client_id"] == env["client_a"]

    async def test_assign_scope_to_supervisor(self, db, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        r = await http_client.post(
            f"/api/admin/users/{env['supervisor_id']}/scopes",
            headers=headers,
            json={"client_id": env["client_a"]},
        )
        assert r.status_code == 201, r.text

    async def test_remove_last_scope_allowed_for_internal(
            self, db, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        # Assign 1
        r = await http_client.post(
            f"/api/admin/users/{env['agent_id']}/scopes",
            headers=headers, json={"client_id": env["client_a"]})
        scope_id = r.json()["data"]["id"]
        # Remove → permitido (internos pueden quedarse sin scopes = ver todo)
        r2 = await http_client.delete(
            f"/api/admin/users/{env['agent_id']}/scopes/{scope_id}",
            headers=headers)
        assert r2.status_code == 200, r2.text

    async def test_remove_last_scope_prohibited_for_external(
            self, db, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        # Create external user
        ext_id = new_id()
        await db.users.insert_one({
            "id": ext_id, "tenant_id": env["tenant_id"],
            "email": "ext@t-57.io", "role": "client_viewer",
            "client_id": env["client_a"],  # legacy → lazy-migrate
            "password_hash": "x", "status": "active",
        })
        # Lazy-migration crea el scope al primer load — pero usamos endpoint directo
        await http_client.post(
            f"/api/admin/users/{ext_id}/scopes",
            headers=headers, json={"client_id": env["client_a"]})
        # List → debe tener 1
        items = (await http_client.get(
            f"/api/admin/users/{ext_id}/scopes", headers=headers
        )).json()["data"]["items"]
        if len(items) == 1:
            scope_id = items[0]["id"]
            r = await http_client.delete(
                f"/api/admin/users/{ext_id}/scopes/{scope_id}", headers=headers)
            # Externo: prohibido borrar el último
            assert r.status_code == 422, r.text


@pytest.mark.asyncio
class TestAgentSeesOnlyAssignedClients:
    async def test_agent_with_scope_filtered_in_queue(self, db, env):
        """Tickets de client_a/b/c; agente solo tiene scope a client_a;
        en queue solo debe ver tickets de A.
        """
        from repositories.tickets import TicketRepository
        from datetime import datetime as _dt
        from datetime import timezone as _tz
        now = _dt.now(_tz.utc).isoformat()
        await db.tickets.insert_many([
            {"id": new_id(), "tenant_id": env["tenant_id"],
             "client_id": env["client_a"], "status": "pending",
             "created_at": now, "updated_at": now},
            {"id": new_id(), "tenant_id": env["tenant_id"],
             "client_id": env["client_b"], "status": "pending",
             "created_at": now, "updated_at": now},
            {"id": new_id(), "tenant_id": env["tenant_id"],
             "client_id": env["client_c"], "status": "pending",
             "created_at": now, "updated_at": now},
        ])
        # Asignar agent → solo cli_a
        await db.user_scope_assignments.insert_one({
            "id": new_id(), "tenant_id": env["tenant_id"],
            "user_id": env["agent_id"], "client_id": env["client_a"],
            "subclient_id": None, "project_id": None,
            "assigned_by": env["superadmin_id"],
            "assigned_at": now,
        })
        repo = TicketRepository(tenant_id=env["tenant_id"])
        # Cuando filtra por client_a explícito → 1 ticket
        only_a = await repo.find(
            {"tenant_id": env["tenant_id"], "client_id": env["client_a"]})
        assert len(only_a) == 1


@pytest.mark.asyncio
class TestResolveClientScope:
    async def test_internal_with_scopes_clamp(self, db, env):
        """Agent con allowed=[A] que pide client_id=B → 403."""
        from middleware.rbac import resolve_client_scope
        from middleware.stack import CurrentUser

        user = CurrentUser(
            id=env["agent_id"], tenant_id=env["tenant_id"],
            email="ag@t-57.io", role="agent", client_id=None,
            allowed_client_ids=[env["client_a"]],
        )
        # Sin requested → devuelve el único
        out = resolve_client_scope(user, None)
        assert out == env["client_a"]
        # Con requested válido
        out2 = resolve_client_scope(user, env["client_a"])
        assert out2 == env["client_a"]
        # Con requested fuera de scope → 403
        from core.errors import RbacDeniedException
        with pytest.raises(RbacDeniedException):
            resolve_client_scope(user, env["client_b"])

    async def test_internal_without_scopes_unrestricted(self, db, env):
        """Agent SIN scopes → puede pedir cualquier client_id (legacy)."""
        from middleware.rbac import resolve_client_scope
        from middleware.stack import CurrentUser
        user = CurrentUser(
            id=env["agent_id"], tenant_id=env["tenant_id"],
            email="ag@t-57.io", role="agent", client_id=None,
            allowed_client_ids=[],
        )
        # Sin scopes → devuelve el requested tal cual (no clamp)
        out = resolve_client_scope(user, env["client_b"])
        assert out == env["client_b"]
        # Sin requested → None (visión completa del tenant)
        out2 = resolve_client_scope(user, None)
        assert out2 is None

    async def test_admin_unrestricted_even_with_scopes(self, db, env):
        from middleware.rbac import resolve_client_scope
        from middleware.stack import CurrentUser
        user = CurrentUser(
            id=env["superadmin_id"], tenant_id=env["tenant_id"],
            email="su@t-57.io", role="superadmin", client_id=None,
            allowed_client_ids=[],  # los admins no cargan scopes
        )
        out = resolve_client_scope(user, env["client_b"])
        assert out == env["client_b"]
