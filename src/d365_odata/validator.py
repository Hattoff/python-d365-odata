
from __future__ import annotations

from .metadata import EntityType
from .types import OrderByItem, FunctionDef
from .expand import ExpandItem, ExpandQuery
from .targets import FromTarget, EntityDefinitionsTarget, WhoAmITarget, FunctionTarget, MetadataTarget
from .metadata import ServiceMetadata
from .ast import (
    Expr, Prop, Literal,
    And, Or, Not,
    Eq, Ne, Gt, Ge, Lt, Le,
    Contains, StartsWith, EndsWith
)

from typing import Optional, Any
from .utilities import _is_guid

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .query import ODataQuery


class ValidationError(ValueError):
    pass

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
    

def validate_target(query: "ODataQuery", metadata: Optional[ServiceMetadata]) -> None:
    t = query._target
    if t is None:
        raise ValidationError("Query has no target. Call from_(), whoami_(), etc.")

    # Targets that don't require metadata
    if isinstance(t, (WhoAmITarget, MetadataTarget, EntityDefinitionsTarget)):
        return

    # Targets that require metadata
    if metadata is None:
        raise ValidationError(f"{t.__class__.__name__} requires metadata, but none was provided.")

    if isinstance(t, FromTarget):
        if t.entity_set not in metadata.entity_sets:
            raise ValidationError(f"Unknown entity set: {t.entity_set!r}")
        return

    if isinstance(t, FunctionTarget):
        fn = metadata.function_for_api(t.api_name)

        # required parameters
        for pname, p in fn.params.items():
            if not p.is_optional and pname not in t.params:
                raise ValidationError(f"Missing required parameter {pname!r} for function {fn.api_name!r}")

        # unknown parameters
        for provided in t.params.keys():
            if provided not in fn.params:
                raise ValidationError(f"Unknown parameter {provided!r} for function {fn.api_name!r}")

        # type checking
        for pname, val in t.params.items():
            expected = fn.params[pname].edm_type
            if not _value_matches_edm(val, expected):
                raise ValidationError(
                    f"Parameter {pname!r} for function {fn.api_name!r} expected {expected}, got {type(val).__name__}"
                )

        return
    raise ValidationError(f"Unsupported target type for validation: {type(t).__name__}")

def _value_matches_edm(value: Any, edm_type: str) -> bool:
    if value is None:
        return True

    if edm_type == "Edm.String":
        return isinstance(value, str)
    if edm_type == "Edm.Boolean":
        return isinstance(value, bool)
    if edm_type in ("Edm.Int32", "Edm.Int16", "Edm.Int64"):
        return isinstance(value, int) and not isinstance(value, bool)
    if edm_type in ("Edm.Decimal", "Edm.Double", "Edm.Single"):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if edm_type == "Edm.Guid":
        return isinstance(value, str) and _is_guid(value)
    # don't block unknown EDM types for now
    return True

class FunctionParamsBuilder:
    def __init__(self, query: "ODataQuery", fn: FunctionDef):
        self._q = query
        self._fn = fn

        # Build lookup tables once
        self._param_names = set(fn.params.keys())  # e.g. {"Target", "FieldName"}
        self._public_to_real: dict[str, str] = {}

        for real in self._param_names:
            # public: _Target and _target
            self._public_to_real[f"_{real}"] = real
            self._public_to_real[f"_{real.lower()}"] = real

    @property
    def done_(self) -> "ODataQuery":
        return self._q

    def __dir__(self):
        # show parameter setters + query methods for completion
        return sorted(set(dir(self._q)) | set(self._public_to_real.keys()) | set(super().__dir__()))

    def __getattr__(self, name: str):
        # 1) Parameter setters: ._Target(...), ._target(...)
        real = self._public_to_real.get(name)
        if real is not None:
            def setter(value):
                expected = self._fn.params[real].edm_type
                if not _value_matches_edm(value, expected):
                    raise TypeError(f"{real} expects {expected}, got {type(value).__name__}")

                t = self._q._target
                if not isinstance(t, FunctionTarget):
                    raise RuntimeError("params builder used without a FunctionTarget")

                new_params = dict(t.params)
                new_params[real] = value
                self._q._target = FunctionTarget.create(t.api_name, **new_params)

                return self  # keep chaining on builder

            return setter

        # 2) Anything else: forward to ODataQuery, preserving fluent chaining
        attr = getattr(self._q, name)
        if callable(attr):
            def wrapped(*args, **kwargs):
                res = attr(*args, **kwargs)
                return self if res is self._q else res
            return wrapped
        return attr



