"""Bulk-close transactions — Bundle A · FIX-A1.

Append-only collection that records every bulk close/change_status execution
so the user has a 30s undo window. Follows the same contract as
`timeline_events` (R04): inserts and *narrow* updates only on
`undone_at` and `undo_partial`. No deletes.

Why a dedicated collection?
- timeline_events is per-ticket; this is per-execution (1 row = N tickets).
- We need ownership + window expiration tracking that doesn't fit timeline.
- Compliance: tamper-resistant record of every mass action.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.db import get_db
from core.uuid import new_id

from .append_only import _AppendOnlyRepository

# Undo window in seconds — kept in code to satisfy the prompt's contract.
BULK_UNDO_WINDOW_SECONDS = 30


class BulkCloseTransactionsRepository(_AppendOnlyRepository):
    collection_name = "bulk_close_transactions"

    async def create(
        self,
        *,
        user_id: str,
        action_type: str,  # "close" | "change_status"
        tickets_count: int,
        ticket_ids: list[str],
        previous_states: list[dict],
        target_status: Optional[str] = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(seconds=BULK_UNDO_WINDOW_SECONDS)
        doc = {
            "id": new_id(),
            "tenant_id": self.tenant_id,
            "user_id": user_id,
            "action_type": action_type,
            "target_status": target_status,
            "executed_at": now.isoformat(),
            "tickets_count": tickets_count,
            "ticket_ids": list(ticket_ids),
            "previous_states": list(previous_states),
            "undo_window_end": window_end.isoformat(),
            "undone_at": None,
            "undo_partial": False,
            "created_at": now.isoformat(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def find_by_id(self, transaction_id: str) -> Optional[dict]:
        return await self.col.find_one(
            {"id": transaction_id, "tenant_id": self.tenant_id},
            {"_id": 0},
        )

    async def mark_undone(
        self, transaction_id: str, *, partial: bool,
    ) -> None:
        """Narrow update: only `undone_at` and `undo_partial`.

        R04-analogue: no other fields may be modified post-insert.
        """
        await self.col.update_one(
            {"id": transaction_id, "tenant_id": self.tenant_id},
            {"$set": {
                "undone_at": datetime.now(timezone.utc).isoformat(),
                "undo_partial": partial,
            }},
        )
