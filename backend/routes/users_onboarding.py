"""Onboarding tour state — per-user persistence.

Endpoints:
  GET  /api/users/me/onboarding             retrieve current user's flag
  POST /api/users/me/onboarding/complete    mark tour as seen
  POST /api/users/me/onboarding/reset       re-trigger the tour (e.g. from
                                            an avatar menu "Volver a ver tour")

Storage: a single boolean `onboarding_completed` on the user document.
Default `False` for new users → tour fires automatically on first login.
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from core.db import get_db
from core.response import ok


router = APIRouter(prefix="/api/users/me/onboarding", tags=["users-onboarding"])


def _suggested_tour(role: str) -> str:
    """Pick the right tour preset for the user's role."""
    if role in ("root_dev", "superadmin"):
        return "root_dev"
    if role in ("admin", "coordinator"):
        return "admin"
    if role in ("agent", "supervisor"):
        return "agent"
    return "agent"  # safe default for client_viewer/auditor: they see /agente


@router.get("")
async def get_status(request: Request):
    user = request.state.user
    db = get_db()
    doc = await db.users.find_one({"id": user.id}, {"_id": 0,
        "onboarding_completed": 1, "onboarding_completed_at": 1})
    completed = bool((doc or {}).get("onboarding_completed", False))
    return ok({
        "completed": completed,
        "completed_at": (doc or {}).get("onboarding_completed_at"),
        "role": user.role,
        "suggested_tour": _suggested_tour(user.role),
    })


@router.post("/complete")
async def complete(request: Request):
    user = request.state.user
    await get_db().users.update_one(
        {"id": user.id},
        {"$set": {
            "onboarding_completed": True,
            "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return ok({"completed": True})


@router.post("/reset")
async def reset(request: Request):
    user = request.state.user
    await get_db().users.update_one(
        {"id": user.id},
        {"$set": {"onboarding_completed": False},
         "$unset": {"onboarding_completed_at": ""}},
    )
    return ok({"completed": False,
                "suggested_tour": _suggested_tour(user.role)})
