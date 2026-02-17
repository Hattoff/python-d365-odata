
from __future__ import annotations

from .metadata import EntityType
from .types import OrderByItem
from .expand import ExpandItem, ExpandQuery
from .targets import FromTarget, EntityDefinitionsTarget, WhoAmITarget, EdmxTarget
from .metadata import ServiceMetadata
from .ast import (
    Expr, Prop, Literal,
    And, Or, Not,
    Eq, Ne, Gt, Ge, Lt, Le,
    Contains, StartsWith, EndsWith,
    _CoercingBinary, _StrictBinary
)

from typing import Optional, Any, Dict
from .utilities import _is_guid

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .query import ODataQueryBuilder


class ValidationError(ValueError):
    pass

# ------- EDM Type Validation -------- #

def wrap_edm_type(value: Any, expected_type: str):
    if isinstance(value, Expr):
        return value
    if expected_type == ("Edm.String"):
        return Literal(value)
    else:
        return Prop(value)

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

# ------- Query Part Validation -------- #

def validate_select(select_fields: list[str], entity_type: EntityType) -> None:
    for f in select_fields:
        if f not in entity_type.properties:
            raise ValueError(f"Unknown property in $select: '{f}' on '{entity_type.name}'")


def validate_orderby(orderby: list[OrderByItem], entity_type: EntityType) -> None:
    for it in orderby:
        if it.field not in entity_type.properties:
            raise ValueError(f"Unknown property in $orderby: '{it.field}' on '{entity_type.name}'")

def validate_binary_expr(expr: Expr, target_entity: str, metadata: ServiceMetadata):
    left = expr.left
    right = expr.right
    if isinstance(left, Prop) and isinstance(right, Prop):
        raise TypeError("Expected the binary expression to be a prop and a literal")
    
    if isinstance(left, Literal) and isinstance(right, Literal):
        raise TypeError("Expected the binary expression to be a prop and a literal")

    if isinstance(left, Prop):
        prop_is_left = True
        prop_expr = left
    else:
        prop_is_left = False
        prop_expr = right

    attr, attr_name = metadata.get_attribute(prop_expr.name, entity_name=target_entity)
    is_valid = False
    validated_expr = None
    if attr:
        type_element = attr.get("type_element")
        if type_element == "enum_type":
            validated_expr, is_valid = validate_enum(expr=expr, prop_is_left=prop_is_left, attr=attr, metadata=metadata)
        if type_element == "edm":
            lit_expr = right if prop_is_left else right
            is_valid = _value_matches_edm(lit_expr.value, attr.get("full_type"))
    if not is_valid:
        raise TypeError("Binary expression is invalid")
    return validated_expr
    
def validate_enum(expr: Expr, prop_is_left: bool, attr: Any, metadata: ServiceMetadata):
    is_valid = False
    validated_expr = None
    enum, enum_name = metadata.get_enum(attr.get("type"))
    if enum:
        left = expr.left
        right = expr.right
        lit_expr = right if prop_is_left else right
        enum_info = metadata.get_enum_info(enum_name, enum_variable=lit_expr.value)
        if enum_info:
            expr_class = type(expr)
            replacement_lit_prop = Prop(f"{enum_info.get("enum_path")}'{enum_info.get("enum_member")}'")
            if prop_is_left:
                validated_expr = expr_class(left=left, right=replacement_lit_prop)
            else:
                validated_expr = expr_class(left=replacement_lit_prop, right=right)
            is_valid = True
    return validated_expr, is_valid

def validate_prop(prop_expr: Prop, target_entity: str, metadata: ServiceMetadata):
    if not isinstance(prop_expr, Prop):
        raise TypeError("Expected a prop type...")
    
    attr, attr_name = metadata.get_attribute(prop_expr.name, entity_name=target_entity)
    if attr:
        return True
    
    return False

def validate_expr(expr: Expr, target_entity: str, metadata: ServiceMetadata) -> None:
    """
    Validate expression
    
    :param expr: Description
    :type expr: Expr
    :param entity_type: Description
    :type entity_type: EntityType
    """
    # Walk the AST and ensure entity property or attribute exists
    # TODO: Potentially decode/encode stringmaps
    if isinstance(expr, Prop):
       if validate_prop(expr, target_entity, metadata):
           return
    if isinstance(expr, Literal):
        return

    # Handle n-tuple And/Or
    # if isinstance(expr, And) or isinstance(expr, Or):
    #     for t in expr.terms:
    #         validate_expr(t, entity_type)
    #     return

    # Binary nodes
    # TODO: use the new binary classes to identify these in general
    if isinstance(expr, _CoercingBinary) or isinstance(expr, _StrictBinary):
        validate_binary_expr(expr, target_entity, metadata)
        return

    # if isinstance(expr, Not):
    #     validate_expr(expr.expr, entity_type)
    #     return

    raise TypeError(f"Unknown expression node: {type(expr)!r}")


def validate_query(q: ODataQueryBuilder) -> None:
    """
    Validate query parts individually
    
    :param q: Query to validate
    :type q: ODataQuery
    :param entity_type: Entity being queried
    :type entity_type: EntityType
    """
    # Validate select
    # for f in q._select:
    #     if f not in entity_type.properties:
    #         raise ValueError(f"Unknown property in $select: '{f}' on '{entity_type.name}'")

    # Validate filter
    if q._filter is not None:
        if q._target and isinstance(q._target, FromTarget):
            validate_expr(q._filter, q._target.entity_set, q._metadata)

    # Validate order by
    # for it in q._orderby:
    #     if it.field not in entity_type.properties:
    #         raise ValueError(f"Unknown property in $orderby: '{it.field}' on '{entity_type.name}'")

    # Validate skip
    if q._skip is not None and q._skip < 0:
        raise ValueError("$skip must be non-negative")
    
    # Validate top
    if q._top is not None and q._top < 0:
        raise ValueError("$top must be non-negative")
    

def validate_odata(q: ODataQueryBuilder) -> None:
    """
    Validate query parts individually
    
    :param q: Query to be validated
    :type q: ODataQueryBuilder
    :param metadata: Metadata from service
    :type metadata: Optional[ServiceMetadata]
    """

    validate_target(q)


    # Validate select
    # for f in q._select:
    #     if f not in entity_type.properties:
    #         raise ValueError(f"Unknown property in $select: '{f}' on '{entity_type.name}'")

    # # Validate filter
    # if q._filter is not None:
    #     validate_expr(q._filter, entity_type)

    # # Validate order by
    # for it in q._orderby:
    #     if it.field not in entity_type.properties:
    #         raise ValueError(f"Unknown property in $orderby: '{it.field}' on '{entity_type.name}'")

    # # Validate skip
    # if q._skip is not None and q._skip < 0:
    #     raise ValueError("$skip must be non-negative")
    
    # # Validate top
    # if q._top is not None and q._top < 0:
    #     raise ValueError("$top must be non-negative")
    

def validate_target(query: "ODataQueryBuilder") -> None:
    t = query._target
    if t is None:
        raise ValidationError("Query has no target. Call from_(), whoami_(), etc.")

    # Targets that don't require metadata
    if t.validate_requires_metadata == False:
        # TODO: Might still pass it through some sort of validation
        return

    # Targets that require metadata
    if query._metadata is None:
        raise ValidationError(f"{t.__class__.__name__} requires metadata for validation, but none was provided.")

    if isinstance(t, FromTarget):
        entity_set_name = query._metadata.ensure_entity_set_name(t.entity_set)
        if entity_set_name is not None and t.entity_set != entity_set_name:
            t._force_update_entity_set(entity_set_name)
        else:
            raise ValidationError(f"Unknown entity set: {t.entity_set!r}")
        return

    raise ValidationError(f"Unsupported target type for validation: {type(t).__name__}")