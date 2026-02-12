from __future__ import annotations
from typing import Any, List
from collections.abc import Iterable as IterableABC
from .types import OrderByItem

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .ast import Expr


# ------- Expresion, Select, and Order-By input helpers -------- #

def flatten_exprs(*items: Any) -> List[Expr]:
    """
    Accepts Expr objects and iterables of Expr (nested allowed) and returns a flat list.

    Examples:
      flatten_exprs(expr1, [expr2, expr3], (expr4, [expr5]))
    
    :param items: Any assortment of Expressions, Lists, Sets, or other iterable containers
    :type items: Any
    :return: A flattened list of expressions
    :rtype: List[Expr]
    """
    out: List[Expr] = []

    def walk(x: Any) -> None:
        if x is None:
            return

        # Strings are not valid here
        if isinstance(x, str):
            raise TypeError("Expected Expr or iterable[Expr], got str")

        if not isinstance(x, IterableABC):
            out.append(x)  # type: ignore[list-item]
            return

        # Iterables: recurse
        # Stabilize sets
        if isinstance(x, set):
            for y in sorted(x, key=repr):
                walk(y)
        else:
            for y in x:
                walk(y)

    for item in items:
        walk(item)

    return out

def flatten_fields(*items: Any) -> List[str]:
        """
        Accepts strings and iterables of strings (including nested),
        returns a deduped list of field names.
        """
        out: List[str] = []
        seen: set[str] = set()

        def add_one(s: str) -> None:
            s2 = s.strip()
            if not s2:
                return
            if s2 not in seen:
                seen.add(s2)
                out.append(s2)

        def walk(x: Any) -> None:
            if x is None:
                return
            # Strings are iterable, but we want to treat them as atomic.
            if isinstance(x, str):
                add_one(x)
                return
            # Walk sets to preserve order
            if isinstance(x, set):
                for y in sorted(x):
                    walk(y)
                return
            # Treat other iterables (lists, tuples, generators, etc.) as collections of fields.
            if isinstance(x, IterableABC):
                for y in x:
                    walk(y)
                return
            # Anything else is a usage error.
            raise TypeError(f"select() expected str or iterable[str], got {type(x).__name__}: {x!r}")

        for item in items:
            walk(item)

        return out
    
def flatten_orderby(*items: Any) -> List[OrderByItem]:
    """
    Compile a variety of input forms into a single, deduplicated list of (field, desc) keys.
    
    :param items:
    - "Name" / "Name desc" / ("Name", "desc") / ("Name", True)
    - "Name asc" / ("Name", "asc") / ("Name", False)
    - [ ... ] / set(...) / nested combos
    :type items: Any
    :return: Returns stable-order list; duplicates removed by final (field, desc) key.
    :rtype: List[OrderByItem]
    """

    order_map: dict[str, bool] = {}   # field -> desc
    order_sequence: list[str] = []    # first-seen order of fields
    
    def add(field: str, desc: bool) -> None:
        f = field.strip()
        if not f:
            return

        if f not in order_map:
            order_sequence.append(f)

        # last one wins
        order_map[f] = desc

    def walk(x: Any) -> None:
        if x is None:
            return

        # String forms: "Name", "Name desc", "Name asc"
        if isinstance(x, str):
            parts = x.strip().split()
            if len(parts) == 1:
                add(parts[0], False)
                return
            if len(parts) == 2 and parts[1].lower() in ("asc", "desc"):
                add(parts[0], parts[1].lower() == "desc")
                return
            raise ValueError(f"Invalid orderby string: {x!r} (use 'Field' or 'Field asc|desc')")
        
        # Tuple/list pair: ("Name", "desc") or ("Name", True)
        if isinstance(x, (tuple, list)) and len(x) == 2 and isinstance(x[0], str):
            field = x[0]
            d = x[1]
            if isinstance(d, bool):
                add(field, d)
                return
            if isinstance(d, str) and d.lower() in ("asc", "desc"):
                add(field, d.lower() == "desc")
                return
            raise ValueError(f"Invalid orderby tuple: {x!r} (second item must be bool or 'asc'/'desc')")

        # Other iterables: recurse
        if isinstance(x, IterableABC):
            # stabilize set ordering
            if isinstance(x, set):
                for y in sorted(x):
                    walk(y)
            else:
                for y in x:
                    walk(y)
            return

        raise TypeError(f"orderby() expected str/tuple/iterable, got {type(x).__name__}: {x!r}")

    for item in items:
        walk(item)

    # rebuild stable ordered list using final directions
    return [OrderByItem(f, order_map[f]) for f in order_sequence]