from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, FrozenSet, Protocol, ClassVar, Mapping, Any
from .utilities import _normalize_guid, _is_guid
from .types import QueryPart

# ------- Targets -------- #

class Target(Protocol):
    """
    A typed-template for any Target-like class.
    Anything that has allowed_parts and to_path() will be classified as a Target.
    """
    allowed_parts: FrozenSet[QueryPart]
    validate_requires_metadata: bool
    def to_path(self) -> str:
        pass

@dataclass(frozen=True)
class BaseTarget:
    """
    Base class for Targets.
    Query targets are often the entry point of the query.
    For example: Target a specific entity (FromTarget) or target a metadata endpoint (EntityDefinitions)
    """
    allowed_parts: FrozenSet[QueryPart]
    """allowed_parts must be overridden"""
    validate_requires_metadata: bool

    def to_path(self) -> str:
        raise NotImplementedError

@dataclass(frozen=True)
class FromTarget(BaseTarget):
    entity_set: str
    id: Optional[Any] = None
    """guid string, no quotes in URL"""

    @staticmethod
    def create(entity_set: str, id: Optional[Any] = None) -> "FromTarget":
        if id is not None and not _is_guid(id):
            raise ValueError(f"Invalid GUID for entity id: {id!r}")
        return FromTarget(
            validate_requires_metadata=True,
            allowed_parts=frozenset({
                QueryPart.SELECT, QueryPart.FILTER, QueryPart.ORDERBY,
                QueryPart.SKIP, QueryPart.TOP, QueryPart.COUNT, QueryPart.EXPAND
            }),
            entity_set=entity_set,
            id=id,
        )

    def to_path(self) -> str:
        if self.id:
            return f"/{self.entity_set}({_normalize_guid(self.id)})"
        return f"/{self.entity_set}"

@dataclass(frozen=True)
class EntityDefinitionsTarget(BaseTarget):
    """
    Hard-coded to allow for fetching of system data necessary for metadata construction.
    Query the EntityMetadata entity exposed by this EntitySet.
    """
    logical_name: Optional[str] = None
    id: Optional[str] = None
    """guid string, no quotes in URL"""

    @staticmethod
    def create(entity_id: Optional[str] = None) -> "EntityDefinitionsTarget":
        logical_name = None
        id = None
        if entity_id:
            if _is_guid(entity_id):
                id = entity_id
            else:
                logical_name = entity_id

        return EntityDefinitionsTarget(
            validate_requires_metadata=False,
            allowed_parts=frozenset({QueryPart.SELECT}),
            logical_name=logical_name,
            id=id,
        )

    def to_path(self) -> str:
        if self.id:
            return f"/EntityDefinitions({_normalize_guid(self.id)})"
        if self.logical_name:
            escaped = self.logical_name.replace("'", "''")
            return f"/EntityDefinitions(LogicalName='{escaped}')"
        return "/EntityDefinitions"

@dataclass(frozen=True)
class EdmxTarget(BaseTarget):
    """
    Hard-coded to allow for fetching of system data necessary for metadata construction.
    Query the $Metadata endpoint for Edmx (XML) document.
    """
    @staticmethod
    def create() -> "EdmxTarget":
        return EdmxTarget(
            validate_requires_metadata=False,
            allowed_parts=frozenset({QueryPart.__NONE__})
        )

    def to_path(self) -> str:
        return "/$Metadata"
    
@dataclass(frozen=True)
class WhoAmITarget(BaseTarget):
    """
    Hard-coded to allow for endpoint testing before metadata construction.
    """
    @staticmethod
    def create() -> "WhoAmITarget":
        return WhoAmITarget(
            validate_requires_metadata=False,
            allowed_parts=frozenset({QueryPart.__NONE__})
        )

    def to_path(self) -> str:
        return "/WhoAmI"