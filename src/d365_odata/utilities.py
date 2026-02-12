from __future__ import annotations
from uuid import UUID


def _is_guid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except Exception:
        return False

def _normalize_guid(value: str) -> str:
    # force lowercase
    return str(UUID(str(value)))
