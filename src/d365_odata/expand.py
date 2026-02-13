from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List

from .ast import Expr, And, Or
from .types import OrderByItem
from .flatten import flatten_fields, flatten_orderby, flatten_exprs

@dataclass
class ExpandQuery:
    """
    A mini-query usable inside $expand=NavProp(...)
    Uses the same shape as ODataQuery but DOES NOT have a main Target.
    """
    _select: List[str] = field(default_factory=list)
    _filter: Optional[Expr] = None
    _count: Optional[bool] = None
    _orderby: List[OrderByItem] = field(default_factory=list)
    _skip: Optional[int] = None
    _top: Optional[int] = None
    _expand: List[ExpandItem] = field(default_factory=list)

    # ------- Select -------- #
    def select_(self, *fields: str) -> "ExpandQuery":
        normalized = flatten_fields(*fields)
        for f in normalized:
            if f not in self._select:
                self._select.append(f)
        return self

    # ------- Criteria -------- #
    def where_(self, *items: Any) -> "ExpandQuery":
        exprs = flatten_exprs(*items)
        if not exprs:
            return self
        incoming: Expr = And(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else And(self._filter, incoming)
        return self

    def or_where_(self, *items: Any) -> "ExpandQuery":
        exprs = flatten_exprs(*items)
        if not exprs:
            return self
        incoming: Expr = Or(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else Or(self._filter, incoming)
        return self

    # ------- Aggregate -------- #
    def count_(self, enabled: bool = True) -> "ExpandQuery":
        self._count = bool(enabled)
        return self

    # ------- Order -------- #
    def orderby_(self, *items: Any) -> "ExpandQuery":
        normalized = flatten_orderby(*items)
        seen = {(i.field, i.desc) for i in self._orderby}
        for it in normalized:
            key = (it.field, it.desc)
            if key not in seen:
                seen.add(key)
                self._orderby.append(it)
        return self

    # ------- Misc -------- #
    def skip_(self, n: int) -> "ExpandQuery":
        if not isinstance(n, int) or n < 0:
            raise ValueError("$skip must be a non-negative integer")
        self._skip = n
        return self

    def top_(self, n: int) -> "ExpandQuery":
        if not isinstance(n, int) or n < 0:
            raise ValueError("$top must be a non-negative integer")
        self._top = n
        return self

    # ------- Expand -------- #
    # Technically support nested expansions but a config will restrict to top-level expansions later.
    # TODO: Implement config and limited expansions.
    def expand_(self, nav: str, sub: Optional["ExpandQuery"] = None) -> "ExpandQuery":
        self._expand.append(ExpandItem(nav=nav, query=sub))
        return self


@dataclass(frozen=True)
class ExpandItem:
    nav: str
    query: Optional[ExpandQuery] = None
