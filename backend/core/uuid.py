"""UUID v4 helper — R19: PKs are CHAR(36) UUID v4."""
from __future__ import annotations
import uuid


def new_id() -> str:
    return str(uuid.uuid4())
