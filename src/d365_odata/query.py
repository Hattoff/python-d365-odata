from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List

from .metadata import ServiceMetadata
from .types import OrderByItem, QueryPart
from .ast import Expr, And, Or
from .compiler import compile_expr, compile_orderby
from .validator import validate_query
from .flatten import flatten_fields, flatten_orderby, flatten_exprs
from .targets import Target, FromTarget, EntityDefinitionsTarget, MetadataTarget, WhoAmITarget

# ------- Query builder -------- #

@dataclass
class ODataQuery:
    # Targets
    _metadata: Optional[ServiceMetadata] = None
    _target: Optional[Target] = None

    # Query options
    _select: List[str] = field(default_factory=list)
    _filter: Optional[Expr] = None
    _count: Optional[bool] = None
    _orderby: List[OrderByItem] = field(default_factory=list)
    _skip: Optional[int] = None
    _top: Optional[int] = None

    # ------- Target -------- #
    def from_(
        self,
        entity_set: str = None,
        metadata: Optional[ServiceMetadata] = None,
        id: Optional[str] = None
    ) -> "ODataQuery":
        if metadata is not None:
            self._metadata = metadata
        self._target = FromTarget.create(entity_set=entity_set, id=id)
        return self

    def entitydefinitions_(
        self,
        entity_id: Optional[str] = None,
        metadata: Optional[ServiceMetadata] = None
    ) -> "ODataQuery":
        if metadata is not None:
            self._metadata = metadata
        self._target = EntityDefinitionsTarget.create(entity_id=entity_id)
        return self
    
    def metadata_(self) -> "ODataQuery":
        self._target = MetadataTarget.create()
        return self
    
    def whoami_(self) -> "ODataQuery":
        self._target = WhoAmITarget.create()
        return self

    # ------- Select -------- #
    def select_(self, *fields: str) -> "ODataQuery":
        normalized = flatten_fields(*fields)
        for f in normalized:
            if f not in self._select:
                self._select.append(f)
        return self

    # ------- Criteria -------- #
    def where_(self, *items: Any) -> "ODataQuery":
        exprs = flatten_exprs(*items)
        if not exprs:
            return self

        incoming: Expr = And(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else And(self._filter, incoming)
        return self

    def or_where_(self, *items: Any) -> "ODataQuery":
        exprs = flatten_exprs(*items)
        if not exprs:
            return self

        incoming: Expr = Or(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else Or(self._filter, incoming)
        return self

    # ------- Expand -------- #
    
    # ------- Aggregate -------- #
    def count_(self, enabled: bool = True) -> "ODataQuery":
        self._count = bool(enabled)
        return self

    # ------- Order -------- #
    def orderby_(self, *items: Any) -> "ODataQuery":
        normalized = flatten_orderby(*items)
        seen = {(i.field, i.desc) for i in self._orderby}
        for it in normalized:
            key = (it.field, it.desc)
            if key not in seen:
                seen.add(key)
                self._orderby.append(it)
        return self

    # ------- Misc -------- #
    def skip_(self, n: int) -> "ODataQuery":
        if not isinstance(n, int) or n < 0:
            raise ValueError("$skip must be a non-negative integer")
        self._skip = n
        return self

    def top_(self, n: int) -> "ODataQuery":
        if not isinstance(n, int) or n < 0:
            raise ValueError("$top must be a non-negative integer")
        self._top = n
        return self
    
    @property
    def _present_parts(self) -> set[QueryPart]:
        present: set[QueryPart] = set()
        if self._select:
            present.add(QueryPart.SELECT)
        if self._filter is not None:
            present.add(QueryPart.FILTER)
        if self._orderby:
            present.add(QueryPart.ORDERBY)
        if self._skip is not None:
            present.add(QueryPart.SKIP)
        if self._top is not None:
            present.add(QueryPart.TOP)
        if self._count is not None:
            present.add(QueryPart.COUNT)
        return present


    def _enforce_allowed_parts(self, target: Target) -> None:
        if QueryPart.__ANY__ in target.allowed_parts:
            return
        
        if self._present_parts and QueryPart.__NONE__ in target.allowed_parts:
            raise ValueError(f"{target.__class__.__name__} does not allow any query parts.")
        
        disallowed = self._present_parts - set(target.allowed_parts)
        if disallowed:
            names = ", ".join(sorted(p.name for p in disallowed))
            raise ValueError(f"{target.__class__.__name__} does not allow: {names}")

    def generate(self, *, validate: bool = True) -> str:
        """
        Compose the query parts into valid syntax.

        :param validate: Optionally choose to validate this syntax agains the metadata provided.
        :type validate: bool
        :return: Return the query string.
        :rtype: str
        """
        self._enforce_allowed_parts(self._target)

        if validate:
            et = self._metadata.entity_type_for_set(self._target.get("entity_set"))
            validate_query(self, et)

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

        base = self._target.to_path()
        return base + (("?" + "&".join(parts)) if parts else "")