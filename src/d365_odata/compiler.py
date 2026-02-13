
from __future__ import annotations
from typing import Any, Sequence
import datetime
from .types import OrderByItem
from .ast import (
    And, Or, Not,
    Eq, Ne, Gt, Ge, Lt, Le,
    Contains, StartsWith, EndsWith,
    Prop, Literal, Expr, In_
)

use_in_operator: bool = False  # default to OR expansion

# ------- Compile to OData -------- #

def compile_expr(expr: Expr) -> str:
    # Add parentheses to ensure logic is mapped correctly
    if isinstance(expr, Prop):
        return expr.name

    if isinstance(expr, Literal):
        return compile_literal(expr.value)

    if isinstance(expr, And):
        inner = " and ".join(compile_expr(t) for t in expr.terms)
        return f"({inner})"
    if isinstance(expr, Or):
        inner = " or ".join(compile_expr(t) for t in expr.terms)
        return f"({inner})"
    
    if isinstance(expr, Not):
        return f"(not {compile_expr(expr.expr)})"

    if isinstance(expr, Eq):
        return f"({compile_expr(expr.left)} eq {compile_expr(expr.right)})"
    if isinstance(expr, Ne):
        return f"({compile_expr(expr.left)} ne {compile_expr(expr.right)})"
    if isinstance(expr, Gt):
        return f"({compile_expr(expr.left)} gt {compile_expr(expr.right)})"
    if isinstance(expr, Ge):
        return f"({compile_expr(expr.left)} ge {compile_expr(expr.right)})"
    if isinstance(expr, Lt):
        return f"({compile_expr(expr.left)} lt {compile_expr(expr.right)})"
    if isinstance(expr, Le):
        return f"({compile_expr(expr.left)} le {compile_expr(expr.right)})"

    if isinstance(expr, Contains):
        return f"contains({compile_expr(expr.haystack)},{compile_expr(expr.needle)})"
    if isinstance(expr, StartsWith):
        return f"startswith({compile_expr(expr.text)},{compile_expr(expr.prefix)})"
    if isinstance(expr, EndsWith):
        return f"endswith({compile_expr(expr.text)},{compile_expr(expr.suffix)})"
    
    if isinstance(expr, In_):
        return compile_in(expr)

    raise TypeError(f"Unknown expression node: {type(expr)!r}")


def compile_literal(value: Any) -> str:
    # OData v4 literal rules
    if value is None:
        return "null"
    if isinstance(value, bool):
        # TODO: tweak this if the property is a two-valued option set or something bool-like (no/yes, 0/1, etc.)
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        # TODO: verify floating point is working as expected
        return str(value)
    if isinstance(value, datetime.datetime):
        # OData v4 uses ISO 8601; assume UTC.
        if value.tzinfo is None:
            return value.isoformat()
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, str):
        # strings use single quotes, with '' escaping
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    # fallback to string
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"

def compile_orderby(items: Sequence[OrderByItem]) -> str:
    # "Name asc,CreatedAt desc"
    chunks = []
    for it in items:
        suffix = " desc" if it.desc else " asc"
        chunks.append(f"{it.field}{suffix}")
    return ",".join(chunks)

def compile_in(node: In_) -> str:
    left = compile_expr(node.left)

    # empty list: choose behavior
    if not node.options:
        return "(false)"

    if use_in_operator:
        # field in (1,2,3)
        inner = ",".join(compile_expr(v) for v in node.options)
        return f"({left} in ({inner}))"

    # default: (field eq 1) or (field eq 2) ...
    parts = [f"({left} eq {compile_expr(v)})" for v in node.options]
    return f"({' or '.join(parts)})"
