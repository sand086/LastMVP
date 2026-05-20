"""RBAC dependencies — applied per route, not globally.

Per MYEXCELLENCE.md sec 8.3, roles ranked from most → least privileged:
    root_dev > superadmin > admin > coordinator > supervisor > agent > client_viewer

``require_role(*roles)`` rejects anyone whose role is not in the allow-list.
``require_min_role("admin")`` checks rank.
"""
from __future__ import annotations

from fastapi import Request

from core.errors import RbacDeniedException, AuthRequiredException

ROLE_RANK = {
    "client_viewer": 1,
    # PROMPT_27 — read-only audit persona (same low rank as client_viewer)
    # Wired explicitly via require_role(...) on AI audit endpoints. NOT covered
    # by require_min_role("agent") and above.
    "client_auditor": 1,
    "agent": 2,
    "supervisor": 3,
    "coordinator": 4,
    "admin": 5,
    "superadmin": 6,
    "root_dev": 7,
}

VALID_ROLES = set(ROLE_RANK)


# Bundle G+ · Reglas de delegación de invitación de usuarios.
#
# Define qué rol puede **crear** (invitar) qué otros roles dentro del tenant.
# Inspirado en `RoleHierarchyRule` del ERD Enterprise, pero implementado como
# config dict (no tabla DB) — mantiene el RBAC simple y testeable.
#
# Reglas:
#   - actor: rol del usuario que invoca POST/PATCH /api/admin/users
#   - can_assign: lista blanca de roles que el actor puede crear/asignar
#   - Coordinators pueden invitar externos (client_viewer/client_auditor) a
#     CUALQUIER client del tenant — la asociación al client_id queda regida
#     por G-03 (validación de existencia) y, en Bundle H, por
#     UserScopeAssignment (clients del coordinator).
#
# Roles NO listados aquí (supervisor, agent, externals) NO pueden invitar a
# nadie.
ASSIGNMENT_RULES: dict[str, set[str]] = {
    "root_dev": {
        "root_dev", "superadmin", "admin", "coordinator",
        "supervisor", "agent", "client_viewer", "client_auditor",
    },
    "superadmin": {
        "admin", "coordinator", "supervisor", "agent",
        "client_viewer", "client_auditor",
    },
    "admin": {
        "coordinator", "supervisor", "agent",
        "client_viewer", "client_auditor",
    },
    "coordinator": {
        # Coordinators sólo invitan externos read-only a su tenant.
        "client_viewer", "client_auditor",
    },
}


def can_assign_role(actor_role: str, target_role: str) -> bool:
    """Bundle G+ — ¿Puede ``actor_role`` crear/asignar ``target_role``?"""
    return target_role in ASSIGNMENT_RULES.get(actor_role, set())


def assignable_roles_for(actor_role: str) -> list[str]:
    """Bundle G+ — Lista los roles que ``actor_role`` puede invitar.

    Usado por el frontend para poblar el dropdown del formulario de creación
    de usuarios (oculta opciones que el actor no puede asignar).
    """
    return sorted(ASSIGNMENT_RULES.get(actor_role, set()),
                  key=lambda r: ROLE_RANK.get(r, 0))


def _user(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise AuthRequiredException()
    return user


def require_role(*roles: str):
    allowed = set(roles)

    async def _dep(request: Request):
        u = _user(request)
        if u.role not in allowed:
            raise RbacDeniedException()
        return u

    return _dep


def require_min_role(min_role: str):
    threshold = ROLE_RANK[min_role]

    async def _dep(request: Request):
        u = _user(request)
        if ROLE_RANK.get(u.role, 0) < threshold:
            raise RbacDeniedException()
        return u

    return _dep


async def require_authenticated(request: Request):
    return _user(request)


def resolve_client_scope(user, requested_client_id: str | None) -> str | list[str] | None:
    """Bundle G+H — Devuelve el ``client_id`` efectivo para una query.

    Bundle G (1:1): los externos tenían UN solo client_id.
    Bundle H (1:N): los externos pueden tener N clients asignados.
    Iter57 (1:N internos): los internos también pueden tener scopes opcionales.

    Comportamiento:
      - **Sin restricción** (admin+, o interno sin user_scopes) honra
        ``requested_client_id`` tal cual.
      - **Restringido** (externo siempre, o interno con scopes definidos):
        clampa al subset permitido.
      - **Restringido + requested in allowed** devuelve ``requested`` (single).
      - **Restringido + requested fuera de allowed** lanza 403.
      - **Restringido + sin requested + 1 allowed** devuelve el str.
      - **Restringido + sin requested + N allowed** devuelve la lista (callers
        la usan con ``{"$in": list}`` o el helper
        :func:`apply_client_scope_filter`).
      - **Externo con scope vacío** lanza 403 (cuenta mal configurada).
    """
    allowed = list(getattr(user, "allowed_client_ids", []) or [])
    is_ext = getattr(user, "is_external", lambda: False)()

    # Sin scopes:
    # - Si es externo: cuenta mal configurada → 403.
    # - Si es interno sin scopes: ve todo el tenant (legacy compat).
    if not allowed:
        if is_ext:
            raise RbacDeniedException(
                "Cuenta externa sin client_id asignado. Contacte al administrador.")
        return requested_client_id

    # Backwards-compat externos: campo legacy users.client_id.
    if is_ext and not allowed and getattr(user, "client_id", None):
        allowed = [user.client_id]
    if is_ext and not allowed:
        raise RbacDeniedException(
            "Cuenta externa sin client_id asignado. Contacte al administrador.")

    # Con scopes (interno o externo): clamp obligatorio.
    if requested_client_id:
        if requested_client_id not in allowed:
            raise RbacDeniedException(
                "client_id solicitado fuera de tu scope.")
        return requested_client_id

    return allowed[0] if len(allowed) == 1 else allowed


def apply_client_scope_filter(query: dict, user, requested_client_id: str | None) -> dict:
    """Bundle H — Aplica el clamp de scope sobre un query dict de Mongo.

    Inyecta ``client_id`` o ``client_id: {"$in": [...]}`` según corresponda.
    Es el wrapper recomendado para endpoints multi-scope.
    """
    scope = resolve_client_scope(user, requested_client_id)
    if scope is None:
        return query
    if isinstance(scope, list):
        query["client_id"] = {"$in": scope}
    else:
        query["client_id"] = scope
    return query


def default_landing_for(role: str) -> str:
    """Sec 3.1 of skill — defaults inteligentes por rol.

    Frontend uses this to pick where to send the user post-login or after /default.

    Iter36: Dashboard es la primera pantalla de operación diaria para roles
    administrativos. Agent/Supervisor/Auditor mantienen su panel especializado.

    Bundle G · G-02: ``client_viewer`` ya **no** aterriza en /dashboard
    (filtraba KPIs cross-client). Va al panel externo read-only.
    """
    return {
        "root_dev": "/dashboard",
        "superadmin": "/dashboard",
        "admin": "/dashboard",
        "coordinator": "/dashboard",
        "supervisor": "/torre",
        "agent": "/agente",
        "client_viewer": "/auditor",      # G-02
        "client_auditor": "/auditor",
    }.get(role, "/default")
