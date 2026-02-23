from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, FrozenSet, Any
from .utilities import _normalize_guid, _is_guid
from .types import QueryPart

# ------- Targets -------- #
@dataclass(frozen=True)
class Target:
    """
    Base class for Targets.
    Query targets are often the entry point of the query.
    For example: Target a specific entity (FromTarget) or target a metadata endpoint (EntityDefinitions)
    """
    allowed_parts: FrozenSet[QueryPart]
    """allowed_parts must be overridden"""
    validate_requires_metadata: bool
    _part_validation_error: Optional[str]

    def to_path(self) -> str:
        raise NotImplementedError
    
    @property
    def target_entity(self):
        raise NotImplementedError

@dataclass(frozen=True)
class FromTarget(Target):
    entity_set: str
    id: Optional[Any] = None
    focus: Optional[str] = None
    """Navigate directly to an entity or collection of entities via a Navigation Property. Note that .select_ will now reference fields from the Focus entity."""
    focus_type: Optional[str] = None
    """If any attributes on the target entity have types which inherit from the Focus attribute, target only those attributes and expand."""
    focus_entity: Optional[str] = None

    @staticmethod
    def create(entity_set: str, id: Optional[Any] = None, focus: Optional[str] = None, focus_type: Optional[str] = None) -> FromTarget:
        # if id is not None and not _is_guid(id):
        #     raise ValueError(f"Invalid GUID for entity id: {id!r}")
        if focus is not None and id is None:
            raise ValueError(f"Use of Focus required an entity id or name.")
        
        if focus is not None or id is not None:
            allowed_parts=frozenset({QueryPart.SELECT, QueryPart.EXPAND})
            part_validation_error = "FROM only allows SELECT and EXPAND when using ID or FOCUS."
        else:
            allowed_parts=frozenset({QueryPart.__ANY__})
            part_validation_error = ""

        return FromTarget(
            validate_requires_metadata=True,
            allowed_parts=allowed_parts,
            entity_set=entity_set,
            id=id,
            focus=focus,
            focus_type=focus_type,
            focus_entity=None,
            _part_validation_error = part_validation_error
        )

    def to_path(self) -> str:
        if self.id:
            if _is_guid(self.id):
                full_path = f"/{self.entity_set}({_normalize_guid(self.id)})"
            else:
                full_path = f"/{self.entity_set}(LogicalName='{self.id}')"
            if self.focus is not None:
                full_path = f"{full_path}/{self.focus}{(f"/{self.focus_type}" if self.focus_type is not None else "")}"
        else:
            full_path = f"/{self.entity_set}"
        return full_path
    
    @property
    def target_entity(self):
        if self.focus_entity is not None:
            return self.focus_entity
        else:
            return self.entity_set
    
    def _update_entity_set(self, val) -> None:
        object.__setattr__(self, 'entity_set', val)

    def _update_focus(self, val) -> None:
        object.__setattr__(self, 'focus', val)

    def _update_focus_type(self, val) -> None:
        object.__setattr__(self, 'focus_type', val)

    def _update_focus_entity(self, val) -> None:
        object.__setattr__(self, 'focus_entity', val)

    def _update_id(self, val) -> None:
        object.__setattr__(self, 'id', val)

@dataclass(frozen=True)
class ExpandTarget(Target):
    navigation_property: str
    entity_set: str
    """Expand type """

    @staticmethod
    def create(navigation_property: str) -> ExpandTarget:
        allowed_parts=frozenset({QueryPart.SELECT, QueryPart.FILTER, QueryPart.EXPAND})

        return ExpandTarget(
            validate_requires_metadata=True,
            allowed_parts=allowed_parts,
            navigation_property=navigation_property,
            entity_set=None,
            _part_validation_error=None
        )

    def to_path(self) -> str:
        return f"{self.navigation_property}"
    
    @property
    def target_entity(self):
        return self.entity_set
    
    def _update_nav_prop(self, val) -> None:
        object.__setattr__(self, 'navigation_property', val)
    
    def _update_entity_set(self, val) -> None:
        object.__setattr__(self, 'entity_set', val)


@dataclass(frozen=True)
class EntityDefinitionsTarget(Target):
    """
    Hard-coded to allow for fetching of system data necessary for metadata construction.
    Query the /EntityDefinitions endpoint.
    """
    logical_name: Optional[str] = None
    id: Optional[str] = None
    """guid string, no quotes in URL"""

    @staticmethod
    def create(entity_id: Optional[str] = None) -> EntityDefinitionsTarget:
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
            _part_validation_error=None
        )

    def to_path(self) -> str:
        if self.id:
            return f"/EntityDefinitions({_normalize_guid(self.id)})"
        if self.logical_name:
            escaped = self.logical_name.replace("'", "''")
            return f"/EntityDefinitions(LogicalName='{escaped}')"
        return "/EntityDefinitions"
    
    @property
    def target_entity(self):
        raise RuntimeError("This target has no target_entity. It should never have been called.")

@dataclass(frozen=True)
class EdmxTarget(Target):
    """
    Hard-coded to allow for fetching of system data necessary for metadata construction.
    Query the /$metadata endpoint for Edmx (XML) document.
    """
    @staticmethod
    def create() -> "EdmxTarget":
        return EdmxTarget(
            validate_requires_metadata=False,
            allowed_parts=frozenset({QueryPart.__NONE__}),
            _part_validation_error=None
        )

    def to_path(self) -> str:
        return "/$metadata"

    @property
    def target_entity(self):
        raise RuntimeError("This target has no target_entity. It should never have been called.")
    
@dataclass(frozen=True)
class WhoAmITarget(Target):
    """
    Hard-coded to allow for endpoint testing before metadata construction.
    Query the /WhoAmI endpoint.
    """
    @staticmethod
    def create() -> WhoAmITarget:
        return WhoAmITarget(
            validate_requires_metadata=False,
            allowed_parts=frozenset({QueryPart.__NONE__}),
            _part_validation_error=None
        )

    def to_path(self) -> str:
        return "/WhoAmI"
    
    @property
    def target_entity(self):
        raise RuntimeError("This target has no target_entity. It should never have been called.")