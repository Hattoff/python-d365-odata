
from __future__ import annotations

from .metadata import EntityType
from .types import OrderByItem
from .expand import ExpandItem, ExpandQuery
from .ast import (
    Expr, Prop, Literal,
    And, Or, Not,
    Eq, Ne, Gt, Ge, Lt, Le,
    Contains, StartsWith, EndsWith
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .query import ODataQuery

# ------- Validation -------- #

def validate_select(select_fields: list[str], entity_type: EntityType) -> None:
    for f in select_fields:
        if f not in entity_type.properties:
            raise ValueError(f"Unknown property in $select: '{f}' on '{entity_type.name}'")


def validate_orderby(orderby: list[OrderByItem], entity_type: EntityType) -> None:
    for it in orderby:
        if it.field not in entity_type.properties:
            raise ValueError(f"Unknown property in $orderby: '{it.field}' on '{entity_type.name}'")

def validate_expr(expr: Expr, entity_type: EntityType) -> None:
    """
    Validate expression
    
    :param expr: Description
    :type expr: Expr
    :param entity_type: Description
    :type entity_type: EntityType
    """
    # Walk the AST and ensure entity property or attribute exists
    # TODO: Implement type checks and enforce/change values as needed
    # TODO: Potentially decode/encode stringmaps
    if isinstance(expr, Prop):
        if expr.name not in entity_type.properties:
            raise ValueError(f"Unknown property in $filter: '{expr.name}' on '{entity_type.name}'")
        return
    if isinstance(expr, Literal):
        return

    # Handle n-tuple And/Or
    if isinstance(expr, And) or isinstance(expr, Or):
        for t in expr.terms:
            validate_expr(t, entity_type)
        return

    # Binary nodes
    # TODO: use the new binary classes to identify these in general
    for bin_type in (Eq, Ne, Gt, Ge, Lt, Le, Contains, StartsWith, EndsWith):
        if isinstance(expr, bin_type):
            validate_expr(expr.left, entity_type)     # type: ignore[attr-defined]
            validate_expr(expr.right, entity_type)    # type: ignore[attr-defined]
            return

    if isinstance(expr, Not):
        validate_expr(expr.expr, entity_type)
        return

    raise TypeError(f"Unknown expression node: {type(expr)!r}")


def validate_query(q: ODataQuery, entity_type: EntityType) -> None:
    """
    Validate query parts individually
    
    :param q: Query to validate
    :type q: ODataQuery
    :param entity_type: Entity being queried
    :type entity_type: EntityType
    """
    # Validate select
    for f in q._select:
        if f not in entity_type.properties:
            raise ValueError(f"Unknown property in $select: '{f}' on '{entity_type.name}'")

    # Validate filter
    if q._filter is not None:
        validate_expr(q._filter, entity_type)

    # Validate order by
    for it in q._orderby:
        if it.field not in entity_type.properties:
            raise ValueError(f"Unknown property in $orderby: '{it.field}' on '{entity_type.name}'")

    # Validate skip
    if q._skip is not None and q._skip < 0:
        raise ValueError("$skip must be non-negative")
    
    # Validate top
    if q._top is not None and q._top < 0:
        raise ValueError("$top must be non-negative")
    
