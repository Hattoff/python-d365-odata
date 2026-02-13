from __future__ import annotations
from uuid import UUID
from typing import Any

def _is_guid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except Exception:
        return False

def _normalize_guid(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    # force lowercase
    return str(UUID(str(value)))
