from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List

from .metadata import ServiceMetadata
from .types import OrderByItem
from .ast import Expr, And, Or
from .compiler import compile_expr, compile_orderby
from .validator import validate_query, validate_expr, validate_orderby
from .flatten import flatten_fields, flatten_orderby, flatten_exprs
from .target import FromTarget, EntityDefinitionsTarget, _is_guid

# ------- Query builder -------- #

@dataclass
class ODataQuery:
    # Targets
    _metadata: Optional[ServiceMetadata] = None
    _from_target: Optional[FromTarget] = None
    _entitydefs_target: Optional[EntityDefinitionsTarget] = None

    # Query options
    _select: List[str] = field(default_factory=list)
    _filter: Optional[Expr] = None
    _count: Optional[bool] = None
    _orderby: List[OrderByItem] = field(default_factory=list)
    _skip: Optional[int] = None
    _top: Optional[int] = None

    def from_(
        self,
        entity_set: str = None,
        metadata: Optional[ServiceMetadata] = None,
        id: Optional[str] = None
    ) -> "ODataQuery":
        # Targets are mutually exclusive
        if self._entitydefs_target is not None:
            raise ValueError(".from_() cannot be used with .entitydefinitions()")

        if metadata is not None:
            self._metadata = metadata

        if id is not None:
            if not _is_guid(id):
                raise ValueError(f"Invalid GUID for entity id: {id!r}")

        self._from_target = FromTarget(entity_set=entity_set, id=id)
        return self

    def entitydefinitions(
        self,
        entity_id: Optional[str] = None,
        metadata: Optional[ServiceMetadata] = None
    ) -> "ODataQuery":
        # Targets are mutually exclusive
        if self._from_target is not None:
            raise ValueError(".entitydefinitions() cannot be used with .from_()")

        if metadata is not None:
            self._metadata = metadata

        logical_name = None
        id = None

        # If entity_set is supplied, treat as LogicalName (string),
        # but if it looks like a guid and id is missing, treat it as id.
        if entity_id:
            if _is_guid(entity_id):
                id = entity_id
            else:
                logical_name = entity_id

        self._entitydefs_target = EntityDefinitionsTarget(logical_name=logical_name, id=id)
        return self

    def select(self, *fields: str) -> "ODataQuery":
        normalized = flatten_fields(*fields)
        for f in normalized:
            if f not in self._select:
                self._select.append(f)
        return self

    def where(self, *items: Any) -> "ODataQuery":
        exprs = flatten_exprs(*items)
        if not exprs:
            return self

        incoming: Expr = And(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else And(self._filter, incoming)
        return self

    def or_where(self, *items: Any) -> "ODataQuery":
        exprs = flatten_exprs(*items)
        if not exprs:
            return self

        incoming: Expr = Or(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else Or(self._filter, incoming)
        return self

    def count(self, enabled: bool = True) -> "ODataQuery":
        self._count = bool(enabled)
        return self

    def orderby(self, *items: Any) -> "ODataQuery":
        normalized = flatten_orderby(*items)
        seen = {(i.field, i.desc) for i in self._orderby}
        for it in normalized:
            key = (it.field, it.desc)
            if key not in seen:
                seen.add(key)
                self._orderby.append(it)
        return self

    def skip(self, n: int) -> "ODataQuery":
        if not isinstance(n, int) or n < 0:
            raise ValueError("$skip must be a non-negative integer")
        self._skip = n
        return self

    def top(self, n: int) -> "ODataQuery":
        if not isinstance(n, int) or n < 0:
            raise ValueError("$top must be a non-negative integer")
        self._top = n
        return self

    def generate(self, *, validate: bool = True) -> str:
        """
        Compose the query parts into valid syntax.

        :param validate: Optionally choose to validate this syntax agains the metadata provided.
        :type validate: bool
        :return: Return the query string.
        :rtype: str
        """
        # Determine base path
        if self._entitydefs_target is not None:
            base = self._entitydefs_target.to_path()

            # EntityDefinitions are only compatible with $select for now.
            if self._filter is not None or self._orderby or self._skip is not None or self._top is not None or self._count is not None:
                raise ValueError("EntityDefinitions only supports $select in this builder (no $filter/$orderby/$skip/$top/$count).")

            # TODO: validate against metadata passed to the query.
            parts: list[str] = []
            if self._select:
                parts.append("$select=" + ",".join(self._select))
            return base + (("?" + "&".join(parts)) if parts else "")

        if self._from_target is None:
            raise ValueError("No target specified. Call .from_(...) or .entitydefinitions(...).")

        base = self._from_target.to_path()

        if validate:
            if self._from_target is not None:
                et = self._metadata.entity_type_for_set(self._from_target.entity_set)
                validate_query(self, et)
            else:
                if self._filter is not None:
                    validate_expr(self._filter, et)
                validate_orderby(self._orderby, et)

        parts = []
        if self._select:
            parts.append("$select=" + ",".join(self._select))
        if self._filter is not None:
            parts.append("$filter=" + compile_expr(self._filter))
        if self._count is not None:
            parts.append("$count=" + ("true" if self._count else "false"))
        if self._orderby:
            parts.append("$orderby=" + compile_orderby(self._orderby))
        if self._skip is not None:
            parts.append("$skip=" + str(self._skip))
        if self._top is not None:
            parts.append("$top=" + str(self._top))
        return base + (("?" + "&".join(parts)) if parts else "")