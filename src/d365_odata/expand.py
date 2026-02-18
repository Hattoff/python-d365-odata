from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List, FrozenSet

from .ast import Expr, And, Or
from .types import OrderByItem, QueryPart
from .flatten import flatten_fields, flatten_orderby, flatten_exprs

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .query import ODataQueryBuilder

@dataclass
class ExpandQuery:
    """
    A mini-query usable inside $expand=NavProp(...)
    Uses the same shape as ODataQuery but DOES NOT have a main Target.
    """

    def __init__(self, nav: str, parent_query: Optional[ODataQueryBuilder] = None, allowed_parts: Optional[FrozenSet[QueryPart]] = None, validate_requires_metadata: Optional[bool] = True):
        self.parent_query = parent_query
        self._target = nav
        self._select = []
        self._filter = None
        self._count = None
        self._orderby = []
        self._skip = None
        self._top = None
        self._expand = []

        allowed_parts = allowed_parts
        self.validate_requires_metadata = validate_requires_metadata

    # ------- Select -------- #
    def select_(self, *fields: str) -> ExpandQuery:
        normalized = flatten_fields(*fields)
        for f in normalized:
            if f not in self._select:
                self._select.append(f)
        return self

    # ------- Criteria -------- #
    def where_(self, *items: Any) -> ExpandQuery:
        exprs = flatten_exprs(*items)
        if not exprs:
            return self
        incoming: Expr = And(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else And(self._filter, incoming)
        return self

    def or_where_(self, *items: Any) -> ExpandQuery:
        exprs = flatten_exprs(*items)
        if not exprs:
            return self
        incoming: Expr = Or(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else Or(self._filter, incoming)
        return self

    # ------- Aggregate -------- #
    def count_(self, enabled: bool = True) -> ExpandQuery:
        self._count = bool(enabled)
        return self

    # ------- Order -------- #
    def orderby_(self, *items: Any) -> ExpandQuery:
        normalized = flatten_orderby(*items)
        seen = {(i.field, i.desc) for i in self._orderby}
        for it in normalized:
            key = (it.field, it.desc)
            if key not in seen:
                seen.add(key)
                self._orderby.append(it)
        return self

    # ------- Misc -------- #
    def skip_(self, n: int) -> ExpandQuery:
        if not isinstance(n, int) or n < 0:
            raise ValueError("$skip must be a non-negative integer")
        self._skip = n
        return self

    def top_(self, n: int) -> ExpandQuery:
        if not isinstance(n, int) or n < 0:
            raise ValueError("$top must be a non-negative integer")
        self._top = n
        return self

    # ------- Expand -------- #
    # Technically support nested expansions but a config will restrict to top-level expansions later.
    # TODO: Implement config and limited expansions.
    # def expand_(self, nav: str, sub: Optional[ExpandQuery] = None) -> ExpandQuery:
    #     self._expand.append(ExpandItem(nav=nav, query=sub))
    #     return self

    def generate(self, *args, **kwargs):
        return self.parent_query.generate(*args, **kwargs)

@dataclass(frozen=True)
class ExpandItem:
    nav: str
    query: ExpandQuery


    @staticmethod
    def create(nav: str, parent_query: ODataQueryBuilder) -> ExpandQuery:
        allowed_parts=frozenset({
                QueryPart.SELECT, QueryPart.FILTER, QueryPart.ORDERBY,
                QueryPart.SKIP, QueryPart.TOP, QueryPart.COUNT #, QueryPart.EXPAND
            })
                
        query = ExpandQuery(
            validate_requires_metadata=True,
            allowed_parts=allowed_parts,
            nav=nav,
            parent_query=parent_query
        )

        return ExpandItem(nav=nav, query=query)
