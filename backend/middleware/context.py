"""Request-level context — tenant + user are extracted by middlewares
and stashed in ``request.state`` for downstream Controllers/Repositories.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CurrentUser:
    id: str
    tenant_id: str
    email: str
    role: str
    name: str = ""
    # Bundle G · G-01 — para roles externos (client_viewer / client_auditor)
    # este campo "ancla" al usuario a UN único cliente del tenant. None para
    # roles internos (agent+) que pueden ver todos los clientes del tenant.
    # DEPRECATED en Bundle H — usar allowed_client_ids. Se mantiene para
    # backwards-compat con código que aún lee este campo.
    client_id: str | None = None
    # Bundle H · UserScopeAssignment — lista completa de clients permitidos.
    # - Externos: lista cargada desde user_scope_assignments (al menos 1 item).
    # - Internos: lista vacía = visión completa del tenant (sin restricción).
    allowed_client_ids: list[str] = field(default_factory=list)

    def is_root_dev(self) -> bool:
        return self.role == "root_dev"

    def is_external(self) -> bool:
        """Bundle G — externals están restringidos a su scope."""
        return self.role in ("client_viewer", "client_auditor")


@dataclass
class TenantContext:
    id: str
    slug: str
    status: str  # active | maintenance | suspended
