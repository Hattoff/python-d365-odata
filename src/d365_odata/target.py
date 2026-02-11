from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
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


@dataclass(frozen=True)
class FromTarget:
    entity_set: str
    id: Optional[str] = None
    """guid string, no quotes in URL"""

    def to_path(self) -> str:
        if self.id:
            return f"/{self.entity_set}({_normalize_guid(self.id)})"
        return f"/{self.entity_set}"


@dataclass(frozen=True)
class EntityDefinitionsTarget:
    logical_name: Optional[str] = None
    id: Optional[str] = None 
    """guid string, no quotes in URL"""

    def to_path(self) -> str:
        # Always includes /EntityDefinitions
        if self.id:
            return f"/EntityDefinitions({_normalize_guid(self.id)})"
        if self.logical_name:
            # OData key predicate with string value requires quotes
            escaped = self.logical_name.replace("'", "''")
            return f"/EntityDefinitions(LogicalName='{escaped}')"
        return "/EntityDefinitions"