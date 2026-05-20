"""Admin user management — CRUD scoped to the current tenant.

RBAC: root_dev | superadmin only (per user request — iter18). Admins of
individual tenants do NOT manage users; only platform staff does. This is
intentional to centralise rol-changes y prevenir privilege escalation.

Endpoints:
  GET    /api/admin/users                      list with optional filters
  POST   /api/admin/users                      create (auto-generated temp pwd)
  PATCH  /api/admin/users/{id}                 update name/role/status/email
  POST   /api/admin/users/{id}/reset-password  rotate to a new temp password
  DELETE /api/admin/users/{id}                 soft-delete (status=deleted)

Guardrails:
  - Cannot self-degrade rank (no self role-changes that lower your own role).
  - Cannot delete the LAST root_dev/superadmin in the tenant.
  - Email uniqueness enforced at insert time (DB index already exists).
  - Temp passwords are 12 chars, mix of letters/digits/punct, returned ONCE.
"""
from __future__ import annotations
import secrets
import string
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from core.db import get_db
from core.errors import (
    MyEException, ErrorCode, ResourceNotFoundException, RbacDeniedException,
)
from core.response import ok
from core.security import hash_password
from core.uuid import new_id
from middleware.rbac import (
    require_min_role, ROLE_RANK, VALID_ROLES,
    can_assign_role, assignable_roles_for,
)
from services import user_audit_log


def _validation_error(message: str, field: str | None = None) -> MyEException:
    return MyEException(ErrorCode.VALIDATION_FAILED, message, field=field)


def _audit_meta(request: Request) -> dict:
    actor = request.state.user
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else None)
    return {
        "tenant_id": actor.tenant_id,
        "actor_id": actor.id,
        "actor_email": actor.email,
        "actor_role": actor.role,
        "ip": (ip or "").split(",")[0].strip() or None,
        "user_agent": request.headers.get("user-agent"),
    }


router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
# Bundle G+ — bajamos el RBAC mínimo a "coordinator" para permitir que
# coordinadores inviten externos read-only. Los guardrails de quién puede
# invitar a quién están en ASSIGNMENT_RULES (rbac.py) y se aplican en
# cada endpoint con can_assign_role().
_RBAC = require_min_role("coordinator")


# -------------------------- Models --------------------------------------
ManageableRole = Literal[
    "client_viewer", "client_auditor", "agent", "supervisor",
    "coordinator", "admin", "superadmin",
]
# root_dev intentionally NOT manageable from this UI — must be created
# directly via seed for security reasons.

UserStatus = Literal["active", "suspended", "deleted"]


_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=_EMAIL_RE)
    name: str = Field(min_length=1, max_length=120)
    role: ManageableRole
    status: UserStatus = "active"
    client_id: Optional[str] = Field(default=None, max_length=64,
                                      description="Required for client_viewer / client_auditor")


class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, max_length=200, pattern=_EMAIL_RE)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    role: Optional[ManageableRole] = None
    status: Optional[UserStatus] = None
    client_id: Optional[str] = None


# -------------------------- Helpers -------------------------------------
def _gen_temp_password(n: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _public_view(doc: dict) -> dict:
    return {
        "id": doc["id"], "email": doc["email"], "name": doc.get("name"),
        "role": doc.get("role"), "status": doc.get("status", "active"),
        "client_id": doc.get("client_id"),
        "must_reset_password": doc.get("must_reset_password", False),
        "last_login_at": doc.get("last_login_at"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


# -------------------------- Endpoints -----------------------------------
@router.get("")
async def list_users(
    request: Request,
    role: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    _: object = Depends(_RBAC),
):
    db = get_db()
    query: dict = {"tenant_id": request.state.user.tenant_id}
    if role and role in VALID_ROLES:
        query["role"] = role
    if status:
        query["status"] = status
    if q:
        query["email"] = {"$regex": q.lower(), "$options": "i"}
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0}).sort(
        "created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    items = [_public_view(d) for d in docs]
    return ok({
        "items": items, "count": len(items),
        "manageable_roles": list(ManageableRole.__args__),
        # Bundle G+ — lista filtrada según ASSIGNMENT_RULES del actor.
        # El frontend usa esto para poblar el dropdown del form de creación.
        "assignable_roles": assignable_roles_for(request.state.user.role),
    })


@router.post("", status_code=201)
async def create_user(payload: UserCreate, request: Request,
                      _: object = Depends(_RBAC)):
    db = get_db()
    user = request.state.user
    # Bundle G+ — el actor sólo puede invitar roles permitidos por ASSIGNMENT_RULES
    if not can_assign_role(user.role, payload.role):
        raise RbacDeniedException(
            f"Tu rol '{user.role}' no puede invitar usuarios con rol '{payload.role}'.")
    email = payload.email.lower()
    # Email uniqueness within tenant (the global unique index is on
    # tenant_id+email so cross-tenant emails are allowed by design).
    existing = await db.users.find_one(
        {"tenant_id": user.tenant_id, "email": email}, {"_id": 0, "id": 1},
    )
    if existing:
        raise _validation_error(
            "Ya existe un usuario con ese email en este tenant.", field="email")
    if payload.role in ("client_viewer", "client_auditor"):
        if not payload.client_id:
            raise _validation_error(
                "Los roles client_viewer y client_auditor requieren client_id.",
                field="client_id")
        # Bundle G · G-03 — validar que client_id exista DENTRO del tenant.
        client_exists = await db.clients.find_one(
            {"id": payload.client_id, "tenant_id": user.tenant_id},
            {"_id": 0, "id": 1},
        )
        if not client_exists:
            raise _validation_error(
                "client_id no encontrado en este tenant.", field="client_id")
    temp_pwd = _gen_temp_password()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": new_id(), "tenant_id": user.tenant_id,
        "email": email, "name": payload.name,
        "role": payload.role, "status": payload.status,
        "client_id": payload.client_id,
        "password_hash": hash_password(temp_pwd),
        "must_reset_password": True,
        "created_at": now, "updated_at": now,
        "last_login_at": None,
        "created_by": user.id,
    }
    await db.users.insert_one(doc)
    # Bundle H — crear la asignación inicial en user_scope_assignments
    if payload.role in ("client_viewer", "client_auditor") and payload.client_id:
        from repositories.user_scopes import UserScopeRepository
        scope_repo = UserScopeRepository(tenant_id=user.tenant_id)
        await scope_repo.assign(
            user_id=doc["id"], client_id=payload.client_id,
            assigned_by=user.id,
        )
    await user_audit_log.record(
        action="user.create", target_id=doc["id"], target_email=doc["email"],
        before=None, after=doc, **_audit_meta(request),
    )
    pub = _public_view(doc)
    pub["temp_password"] = temp_pwd  # ONLY returned once at creation
    return ok(pub, status_code=201)


@router.patch("/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, request: Request,
                      _: object = Depends(_RBAC)):
    db = get_db()
    actor = request.state.user
    target = await db.users.find_one(
        {"id": user_id, "tenant_id": actor.tenant_id}, {"_id": 0},
    )
    if not target:
        raise ResourceNotFoundException()
    # Guardrail: cannot modify root_dev users from this UI
    if target.get("role") == "root_dev":
        raise RbacDeniedException(
            "Los usuarios root_dev no pueden modificarse desde la UI.")
    # Bundle G+ — actor sólo puede tocar usuarios cuyo rol ACTUAL pueda él asignar
    # (evita que un coordinator edite a un admin).
    if not can_assign_role(actor.role, target["role"]) and target["role"] != actor.role:
        raise RbacDeniedException(
            f"Tu rol '{actor.role}' no puede modificar usuarios con rol '{target['role']}'.")
    # Bundle G+ — si se cambia el rol, también debe poder asignar el NUEVO rol
    if payload.role and not can_assign_role(actor.role, payload.role):
        raise RbacDeniedException(
            f"Tu rol '{actor.role}' no puede asignar el rol '{payload.role}'.")
    # Guardrail: cannot self-degrade
    if user_id == actor.id and payload.role and \
            ROLE_RANK.get(payload.role, 0) < ROLE_RANK.get(actor.role, 0):
        raise _validation_error(
            "No podés bajarte de rol a vos mismo.", field="role")
    updates = payload.model_dump(exclude_none=True)
    if updates.get("email"):
        updates["email"] = updates["email"].lower()
        # uniqueness check
        clash = await db.users.find_one({
            "tenant_id": actor.tenant_id, "email": updates["email"],
            "id": {"$ne": user_id},
        }, {"_id": 0, "id": 1})
        if clash:
            raise _validation_error(
                "Ya existe un usuario con ese email en este tenant.",
                field="email")
    # Bundle G · G-03 — si se cambia role a externo o se cambia client_id,
    # validar que el client_id (nuevo o existente) pertenezca al tenant.
    effective_role = updates.get("role", target.get("role"))
    effective_client_id = updates.get("client_id", target.get("client_id"))
    if effective_role in ("client_viewer", "client_auditor"):
        if not effective_client_id:
            raise _validation_error(
                "Los roles client_viewer y client_auditor requieren client_id.",
                field="client_id")
        client_exists = await db.clients.find_one(
            {"id": effective_client_id, "tenant_id": actor.tenant_id},
            {"_id": 0, "id": 1},
        )
        if not client_exists:
            raise _validation_error(
                "client_id no encontrado en este tenant.", field="client_id")
    if not updates:
        return ok(_public_view(target))
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": user_id}, {"$set": updates})
    refreshed = await db.users.find_one({"id": user_id}, {"_id": 0})
    await user_audit_log.record(
        action="user.update", target_id=user_id, target_email=target["email"],
        before=target, after=refreshed, **_audit_meta(request),
    )
    return ok(_public_view(refreshed))


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: str, request: Request,
                          _: object = Depends(_RBAC)):
    db = get_db()
    actor = request.state.user
    target = await db.users.find_one(
        {"id": user_id, "tenant_id": actor.tenant_id}, {"_id": 0},
    )
    if not target:
        raise ResourceNotFoundException()
    if target.get("role") == "root_dev":
        raise RbacDeniedException(
            "No se puede resetear la password de un root_dev desde la UI.")
    # Bundle G+ — sólo puede resetear pwd de roles que él podría asignar
    if not can_assign_role(actor.role, target["role"]) and target["role"] != actor.role:
        raise RbacDeniedException(
            f"Tu rol '{actor.role}' no puede resetear la password de un '{target['role']}'.")
    temp_pwd = _gen_temp_password()
    await db.users.update_one({"id": user_id}, {"$set": {
        "password_hash": hash_password(temp_pwd),
        "must_reset_password": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "password_reset_by": actor.id,
    }})
    await user_audit_log.record(
        action="user.reset_password", target_id=user_id,
        target_email=target["email"], before=None, after=None,
        **_audit_meta(request),
    )
    return ok({"id": user_id, "temp_password": temp_pwd})


@router.delete("/{user_id}")
async def delete_user(user_id: str, request: Request,
                       _: object = Depends(_RBAC)):
    """Soft-delete: status=deleted (preserves audit trail)."""
    db = get_db()
    actor = request.state.user
    target = await db.users.find_one(
        {"id": user_id, "tenant_id": actor.tenant_id}, {"_id": 0},
    )
    if not target:
        raise ResourceNotFoundException()
    if user_id == actor.id:
        raise _validation_error("No podés eliminarte a vos mismo.")
    if target.get("role") == "root_dev":
        raise RbacDeniedException(
            "Los usuarios root_dev no pueden eliminarse desde la UI.")
    # Bundle G+ — sólo puede eliminar roles que él podría asignar
    if not can_assign_role(actor.role, target["role"]):
        raise RbacDeniedException(
            f"Tu rol '{actor.role}' no puede eliminar un '{target['role']}'.")
    # Last-of-rank guardrail
    if target.get("role") in ("superadmin",):
        remaining = await db.users.count_documents({
            "tenant_id": actor.tenant_id, "role": target["role"],
            "status": {"$ne": "deleted"},
            "id": {"$ne": user_id},
        })
        if remaining == 0:
            raise _validation_error(
                f"No se puede eliminar el último {target['role']} del tenant.")
    await db.users.update_one({"id": user_id}, {"$set": {
        "status": "deleted",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "deleted_by": actor.id,
    }})
    # Bundle H — revocar todos los scopes del usuario al eliminarlo
    from repositories.user_scopes import UserScopeRepository
    await UserScopeRepository(tenant_id=actor.tenant_id).revoke_all(user_id)
    await user_audit_log.record(
        action="user.delete", target_id=user_id, target_email=target["email"],
        before=target, after=None, **_audit_meta(request),
    )
    return ok({"deleted": True, "id": user_id})


# ────────────────────────────────────────────────────────────────────────
#  Bundle H · UserScopeAssignment — multi-cliente para externos
# ────────────────────────────────────────────────────────────────────────
class ScopeAssignBody(BaseModel):
    client_id: str = Field(min_length=36, max_length=36)


async def _validate_scope_action(db, actor, user_id: str) -> dict:
    """Carga el target y aplica los guardrails de can_assign_role.

    Iter57 — Reglas:
      - target debe pertenecer al tenant del actor.
      - target debe ser un rol con scope soportado: externos (client_viewer/
        client_auditor) o internos operativos (agent/supervisor/coordinator).
        Para internos, el scope es OPCIONAL: sin scopes ve todo el tenant;
        con scopes ve solo los clientes asignados.
      - actor debe poder asignar el rol del target (ASSIGNMENT_RULES).
    """
    target = await db.users.find_one(
        {"id": user_id, "tenant_id": actor.tenant_id}, {"_id": 0},
    )
    if not target:
        raise ResourceNotFoundException()
    if target["role"] not in (
        "client_viewer", "client_auditor",
        "agent", "supervisor", "coordinator",
    ):
        raise _validation_error(
            "Los scopes solo se pueden aplicar a roles externos "
            "(client_viewer/client_auditor) o internos operativos "
            "(agent/supervisor/coordinator).",
            field="role")
    if not can_assign_role(actor.role, target["role"]):
        raise RbacDeniedException(
            f"Tu rol '{actor.role}' no puede modificar scopes de un '{target['role']}'.")
    return target


@router.get("/{user_id}/scopes")
async def list_user_scopes(user_id: str, request: Request,
                            _: object = Depends(_RBAC)):
    db = get_db()
    actor = request.state.user
    await _validate_scope_action(db, actor, user_id)
    from repositories.user_scopes import UserScopeRepository
    repo = UserScopeRepository(tenant_id=actor.tenant_id)
    items = await repo.list_for_user(user_id)
    return ok({"items": items, "count": len(items)})


@router.post("/{user_id}/scopes", status_code=201)
async def add_user_scope(user_id: str, payload: ScopeAssignBody,
                          request: Request, _: object = Depends(_RBAC)):
    db = get_db()
    actor = request.state.user
    await _validate_scope_action(db, actor, user_id)
    # Validar que client_id exista en el tenant
    client_exists = await db.clients.find_one(
        {"id": payload.client_id, "tenant_id": actor.tenant_id},
        {"_id": 0, "id": 1},
    )
    if not client_exists:
        raise _validation_error(
            "client_id no encontrado en este tenant.", field="client_id")
    from repositories.user_scopes import UserScopeRepository
    repo = UserScopeRepository(tenant_id=actor.tenant_id)
    doc = await repo.assign(
        user_id=user_id, client_id=payload.client_id,
        assigned_by=actor.id,
    )
    await user_audit_log.record(
        action="user.scope_added",
        target_id=user_id, target_email="",
        before=None, after={"client_id": payload.client_id},
        **_audit_meta(request),
    )
    return ok(doc, status_code=201)


@router.delete("/{user_id}/scopes/{assignment_id}")
async def remove_user_scope(user_id: str, assignment_id: str,
                             request: Request, _: object = Depends(_RBAC)):
    db = get_db()
    actor = request.state.user
    target = await _validate_scope_action(db, actor, user_id)
    from repositories.user_scopes import UserScopeRepository
    repo = UserScopeRepository(tenant_id=actor.tenant_id)
    # Iter57 — Guardrail: no permitir borrar el ÚLTIMO scope **solo** para
    # cuentas EXTERNAS (deben tener al menos 1). Para internos, scope vacío
    # significa "ver todo el tenant" — borrado total permitido.
    if target["role"] in ("client_viewer", "client_auditor"):
        rows = await repo.list_for_user(user_id)
        if len(rows) <= 1:
            raise _validation_error(
                "No se puede eliminar el último scope de un usuario externo. "
                "Asigne otro client_id primero o elimine la cuenta.",
                field="assignment_id")
    deleted = await repo.unassign(user_id=user_id, assignment_id=assignment_id)
    if not deleted:
        raise ResourceNotFoundException()
    await user_audit_log.record(
        action="user.scope_removed",
        target_id=user_id, target_email="",
        before={"assignment_id": assignment_id}, after=None,
        **_audit_meta(request),
    )
    return ok({"deleted": True, "id": assignment_id})
