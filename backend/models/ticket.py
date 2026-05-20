"""Ticket models — PROMPT 05."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

TicketStatus = Literal[
    "pending", "in_progress",
    "waiting_client", "waiting_carrier",
    "resolved", "closed", "claim",
]
Channel = Literal["email", "whatsapp", "api", "internal"]


class TicketAssign(BaseModel):
    agent_id: str = Field(min_length=36, max_length=36)


class TicketStatusChange(BaseModel):
    status: TicketStatus
    reason: Optional[str] = Field(default=None, max_length=500)


class TicketSetSolucion(BaseModel):
    solucion_id: str = Field(min_length=36, max_length=36)
    channel: Channel = "email"
