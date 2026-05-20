"""Bundle H · UserScopeAssignment — multi-cliente para usuarios externos.

Una fila por (user_id, client_id) ⇒ habilita N clients por usuario externo.
Reemplaza el campo legacy `users.client_id` (1:1) por una colección 1:N.

Esquema:
    id          : UUID
    tenant_id   : UUID
    user_id     : UUID  (FK a users.id)
    client_id   : UUID  (FK a clients.id, **siempre presente** en esta iteración)
    subclient_id: UUID | None  (reservado para futuro)
    project_id  : UUID | None  (reservado para futuro)
    assigned_by : UUID | None  (user_id que asignó; None = migración legacy)
    assigned_at : ISO datetime

Índices:
    - Compuesto único (tenant_id, user_id, client_id) — evita duplicados.
    - (tenant_id, user_id) — para lookup en cada request.
"""
from __future__ import annotations
from datetime import datetime, timezone

from .base import BaseRepository
from core.errors import MyEException, ErrorCode


class UserScopeRepository(BaseRepository):
    collection_name = "user_scope_assignments"

    async def list_for_user(self, user_id: str) -> list[dict]:
        return await self.find({"user_id": user_id}, limit=100,
                                sort=[("assigned_at", 1)])

    async def client_ids_for_user(self, user_id: str) -> list[str]:
        rows = await self.list_for_user(user_id)
        return [r["client_id"] for r in rows if r.get("client_id")]

    async def assign(self, *, user_id: str, client_id: str,
                     assigned_by: str | None = None) -> dict:
        # Idempotente: si ya existe, devuelve el existente.
        existing = await self.find_one({
            "user_id": user_id, "client_id": client_id,
        })
        if existing:
            return existing
        return await self.insert({
            "user_id": user_id,
            "client_id": client_id,
            "subclient_id": None,
            "project_id": None,
            "assigned_by": assigned_by,
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        })

    async def unassign(self, *, user_id: str, assignment_id: str) -> int:
        return await self.delete_one({
            "id": assignment_id, "user_id": user_id,
        })

    async def revoke_all(self, user_id: str) -> int:
        """Borra todas las asignaciones del user (al eliminar la cuenta)."""
        result = await self.col.delete_many(self._scope({"user_id": user_id}))
        return result.deleted_count

    @staticmethod
    def validation_error(message: str, field: str | None = None) -> MyEException:
        return MyEException(ErrorCode.VALIDATION_FAILED, message, field=field)
