
from __future__ import annotations
from .targets import FromTarget, ExpandTarget
from .metadata import ServiceMetadata
from .ast import (
    Expr, Prop, Literal,
    And, Or, Not,
    _CoercingBinary, _StrictBinary
)
from typing import Any
from .utilities import _is_guid


import logging
logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .query import Query, QueryBase

class ValidationError(ValueError):
    pass

class ValidationLookupError(LookupError):
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
    is_valid = False
    if value is None:
        return is_valid

    if edm_type == "Edm.String":
        is_valid = isinstance(value, str)
    elif edm_type == "Edm.Boolean":
        is_valid = isinstance(value, bool)
    elif edm_type in ("Edm.Int32", "Edm.Int16", "Edm.Int64"):
        is_valid = isinstance(value, int) and not isinstance(value, bool)
    elif edm_type in ("Edm.Decimal", "Edm.Double", "Edm.Single"):
        is_valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif edm_type == "Edm.Guid":
        is_valid = isinstance(value, str) and _is_guid(value)
    else:
        # don't block unknown EDM types for now
        logger.warning(f"Unhandled edm type encountered: {edm_type}. The type was considered valid by default.")
        is_valid = True
    return is_valid

# ------- Query Part Validation -------- #

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
    if attr:
        type_element = attr.get("type_element")
        if type_element == "enum_type":
            is_valid = validate_enum(expr=expr, prop_is_left=prop_is_left, attr_name=attr_name, attr=attr, metadata=metadata)
        if type_element == "edm":
            lit_expr = right if prop_is_left else left
            lit_is_valid = _value_matches_edm(lit_expr.value, attr.get("full_type"))
            prop_is_valid = validate_prop(prop_expr=prop_expr, target_entity=target_entity, metadata=metadata)
            # If the Literal Expr is a guid, then we need to remove the quotes by chaning it to a Prop.
            if attr.get("type") == "Guid":
                replacement_lit_prop = Prop(lit_expr.value)
                if prop_is_left:
                    expr._rebuild(left=left, right=replacement_lit_prop)
                else:
                    expr._rebuild(left=replacement_lit_prop, right=right)
                logger.info(f"Updated binary expression to {expr}.")
            is_valid = (lit_is_valid and prop_is_valid)
    if not is_valid:
        raise TypeError(f"Binary expression is invalid: {expr}")
    
def validate_enum(expr: Expr, prop_is_left: bool, attr_name:str, attr: Any, metadata: ServiceMetadata) -> bool:
    is_valid = False
    attribute_type = attr.get("type")
    if attribute_type is None:
        raise ValidationError(f"Attribute {attr_name} did not have a type.")
    enum, enum_name = metadata.get_enum(attr.get("type"))
    if enum:
        left = expr.left
        right = expr.right
        lit_expr = right if prop_is_left else left
        enum_info = metadata.get_enum_info(enum_name, enum_variable=lit_expr.value)
        if enum_info:
            replacement_lit_prop = Prop(f"{enum_info.get("enum_path")}'{enum_info.get("enum_member")}'")
            if prop_is_left:
                expr._rebuild(left=left, right=replacement_lit_prop)
            else:
                expr._rebuild(left=replacement_lit_prop, right=right)
            logger.info(f"Updated enumerator expression to {expr}.")
            is_valid = True
        else:
            raise ValidationLookupError(f"Unable to find Enumerator {enum_name} member/value {lit_expr.value} in the metadata.")
    else:
        raise ValidationLookupError(f"Unable to find Enumerator by the name of {attribute_type} in the metadata.")
    return is_valid

def validate_prop(prop_expr: Prop, target_entity: str, metadata: ServiceMetadata) -> bool:
    if not isinstance(prop_expr, Prop):
        raise TypeError("Expected a prop type...")
    attr, attr_name = metadata.get_attribute(prop_expr.name, entity_name=target_entity)
    if attr:
        actual_attr_name, attr_api_name_found = get_attribute_api_name(attr, attr_name)
        if attr_api_name_found:
            logger.info(f"Updated the name of attribute from {prop_expr.name} to {actual_attr_name}.")
            prop_expr._update_name(actual_attr_name)
        return True # TODO: Going to keep this in here because I might have two validation modes, one which raises errors the other which returns T/F.
    else:
        raise ValidationLookupError(f"Unable to find property {prop_expr.name} on entity {target_entity}.")
    
def get_attribute_api_name(attr: Any, name: str):
    if attr:
        if api_name:= attr.get("api_name"):
            if name != api_name:
                return api_name, True
    return name, False

def validate_expr(expr: Expr, target_entity: str, metadata: ServiceMetadata) -> None:
    """
    Validate expressions against the metadata. Nested And/Or Expressions are recursively expanded until a Binary or Unary Expression is found. Naked Props and Literals are considered invalid.
    
    :param expr: Expression to validate
    :type expr: Expr
    :param entity_type: Description
    :type entity_type: EntityType
    """
    # Walk the AST and ensure entity property or attribute exists
    # TODO: Potentially decode/encode stringmaps
    if isinstance(expr, Prop):
        raise ValidationError(f"Naked Prop expression {expr} was found. Expressions should be wrapped in And/Or logic or composed with Unary/Binary operators.")
    if isinstance(expr, Literal):
        raise ValidationError(f"Naked Literal expression {expr} was found. Expressions should be wrapped in And/Or logic or composed with Unary/Binary operators.")

    # Handle n-tuple And/Or by recursively callin this function
    if isinstance(expr, And) or isinstance(expr, Or):
        for t in expr.terms:
            validate_expr(expr=t, target_entity=target_entity, metadata=metadata)
        return

    # Validate binary nodes
    if isinstance(expr, _CoercingBinary) or isinstance(expr, _StrictBinary):
        is_valid = validate_binary_expr(expr, target_entity, metadata)
        return is_valid

    if isinstance(expr, Not):
        validate_expr(expr=expr.inner_expr, target_entity=target_entity, metadata=metadata)
        return

    raise TypeError(f"Unknown expression node: {type(expr)!r}")

def validate_from_target(q: QueryBase, metadata: ServiceMetadata):
    t = q._target
    target_entity = t.target_entity
    entity, entity_name = metadata.get_entity(target_entity)
    if entity:
        entity_set_name = entity.get("entity_set_name")
        if entity_set_name is None:
            raise ValidationLookupError(f"Unable to find the entity set name for {(target_entity)}{(f" ({entity_name})" if entity_name != target_entity else "")}.")
        if target_entity != entity_set_name:
            t._update_entity_set(entity_set_name)
            logger.info(f"Changed the target entity from {target_entity} to {entity_set_name}.")
    else:
        raise ValidationLookupError(f"Unknown entity: {t.target_entity!r}")
    
    if t.focus is not None:
        nav_prop, actual_nav_prop_name = metadata.get_navigation_property(t.focus, entity=entity)
        if nav_prop:
            focus_entity, focus_entity_name = metadata.get_entity(nav_prop.get("to_entity_type"))
            if focus_entity:
                t._update_focus(actual_nav_prop_name)
                t._update_focus_entity(focus_entity_name)
            else:
                focus_err_part = f"Unable to Focus on navigation property {t.focus}" + (f"({actual_nav_prop_name})" if t.focus != actual_nav_prop_name else "")
                raise ValidationLookupError(f"{focus_err_part} because the destination entity ({nav_prop.get("to_entity_type")}) couldn't be found in the metadata.")
        else:
            focus_err_part =  f"Unable to Focus on navigation property {t.focus} on entity {t.target_entity}" + (f"({entity_name})" if t.target_entity != entity_name else "")
            raise ValidationLookupError(focus_err_part)
    return

def validate_expand_target (q: QueryBase, metadata: ServiceMetadata):
    t = q._target
    parent_entity = q.parent._target.target_entity
    nav_prop, nav_prop_name = metadata.get_navigation_property(navigation_property_name=t.navigation_property, entity_name=parent_entity)
    if nav_prop:
        to_entity_name = nav_prop.get("to_entity_type")
        if to_entity_name is None:
            raise ValidationLookupError(f"Navigation Property {nav_prop_name} has no target entity.")
        entity, _ = metadata.get_entity(to_entity_name)
        if entity:
            entity_set_name = (entity.get("entity_set_name") or to_entity_name)
            if t.target_entity != entity_set_name:
                logger.info(f"Changed the expand target entity from {t.target_entity} to {entity_set_name}.")
                t._update_entity_set(entity_set_name)
            if t.navigation_property != nav_prop_name:
                logger.info(f"Changed the expand navigation property from {t.navigation_property} to {nav_prop_name}.")
                t._update_nav_prop(nav_prop_name)
        else:
            raise ValidationLookupError(f"Unknown entity: {t.target_entity!r}")
    else:
        raise ValidationLookupError(f"Unable to lookup expand target nav prop")

def target_validation(q: QueryBase, metadata: ServiceMetadata) -> None:
    t = q._target
    if t is None:
        raise ValidationError("Query has no target. Call from_(), whoami_(), etc.")

    # Targets that don't require metadata
    if t.validate_requires_metadata == False:
        # TODO: Might still pass it through some sort of validation
        return

    # Targets that require metadata
    if metadata is None:
        raise ValidationError(f"{t.__class__.__name__} requires metadata for validation, but metadata is missing.")
    
    if isinstance(t, FromTarget):
        print("trying to validate from target")
        validate_from_target(q, metadata)
    elif isinstance(t, ExpandTarget):
        print("trying to validate expand target")
        validate_expand_target(q, metadata)   
    else:
        raise ValidationError(f"Unsupported target type for validation: {type(t).__name__}")

def select_validation(q: Query, metadata: ServiceMetadata) -> None:
    print(f"here is my target: {q._target}")
    print(f"here is my target_entity: {q._target.target_entity}")
    entity, entity_name = metadata.get_entity(q._target.target_entity)
    if entity:
        if "-" in q._select:
            # With keyword "-" the query will only select the bare minimum number of columns (the primary key).
            q._select = [entity.get("primary_key","")]
        elif "*" in q._select:
            # With keyword "*" the query will select all columns; by not specifying a select statement the default behavior is to pull everything, so clear the list.
            q._select = []
        else:
            for i, field in enumerate(q._select):
                attribute, attribute_name = metadata.get_attribute(field, entity=entity)
                if attribute is None:
                    select_error_part = f"Unable to find attribute {field} on entity {entity_name}" + (f"({q._target.target_entity})" if entity_name != q._target.target_entity else "")
                    if isinstance(q._target, FromTarget) and q._target.focus is not None:
                        raise ValidationLookupError(f"{select_error_part}. You are using Focus, be sure your selected columns are from {entity_name} and not {q._target.entity_set}.")
                    else:    
                        raise ValidationLookupError(select_error_part)
                else:
                    actual_attr_name, attr_api_name_found = get_attribute_api_name(attribute, attribute_name)
                    if attr_api_name_found:
                        q._select[i] = actual_attr_name
    else:
        raise ValidationLookupError(f"Unable to find target entity {q._target.target_entity}")

def orderby_validation(q: QueryBase, metadata: ServiceMetadata) -> None:
    orderby = q._orderby
    for it in orderby:
        attribute, attribute_name = metadata.get_attribute(it.field, entity_name=q._target.target_entity)
        if attribute is None:
            raise ValueError(f"Unknown property in $orderby: '{it.field}' on '{q._target.target_entity}'")
        else:
            if attribute_name != it.field:
                it.field = attribute_name
        
def filter_validation(q: Query, metadata: ServiceMetadata) -> None:
    if q._filter is not None:
        if q._target and isinstance(q._target, FromTarget):
            validate_expr(q._filter, q._target.target_entity, metadata)
        

def query_validation(q: Query, metadata: ServiceMetadata) -> None:
    """
    Validate query parts individually
    
    :param q: Query to validate
    :type q: ODataQuery
    :param entity_type: Entity being queried
    :type entity_type: EntityType
    """
    # Validate target
    target_validation(q, metadata=metadata)

    # Validate selected columns
    select_validation(q, metadata=metadata)

    # Validate filters (where clause)
    filter_validation(q, metadata=metadata)

    # Validate order by
    orderby_validation(q, metadata=metadata)

    # Validate skip
    if q._skip is not None and q._skip < 0:
        raise ValueError("$skip must be non-negative")
    
    # Validate top
    if q._top is not None and q._top < 0:
        raise ValueError("$top must be non-negative")
    