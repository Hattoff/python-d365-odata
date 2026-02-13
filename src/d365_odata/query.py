from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List

from .metadata import ServiceMetadata
from .types import OrderByItem, QueryPart
from .expand import ExpandItem, ExpandQuery
from .ast import Expr, And, Or
from .compiler import compile_expr, compile_orderby, compile_expand
from .validator import validate_query, validate_target, FunctionParamsBuilder
from .flatten import flatten_fields, flatten_orderby, flatten_exprs
from .targets import Target, FromTarget, EntityDefinitionsTarget, EdmxTarget, WhoAmITarget, FunctionTarget

import logging
logger = logging.getLogger(__name__)

# ------- Query wrapper -------- #
@dataclass(frozen=True)
class OData:
    """Wrapper class for ODataQueryBuilder ensures you use the same metadata for each query by locking it."""
    metadata: Optional[ServiceMetadata] = None

    def query(self) -> "ODataQueryBuilder":
        return ODataQueryBuilder(metadata=self.metadata, metadata_lock=True)


# ------- Query builder -------- #
@dataclass
class ODataQueryBuilder:
    _metadata: Optional[ServiceMetadata] = None

    # Query options
    _target: Optional[Target] = None
    _select: List[str] = field(default_factory=list)
    _filter: Optional[Expr] = None
    _count: Optional[bool] = None
    _orderby: List[OrderByItem] = field(default_factory=list)
    _skip: Optional[int] = None
    _top: Optional[int] = None
    _expand: List[ExpandItem] = field(default_factory=list)

    def __init__(self, metadata: Optional[ServiceMetadata] = None, metadata_lock: bool = False):
        self._metadata = metadata
        self._target = None
        self._select = []
        self._filter = None
        self._count = None
        self._orderby = []
        self._skip = None
        self._top = None
        self._expand = []
        self._metadata_lock = metadata_lock

    # Optional way to implement the metadata while building the query.
    def using_(self, metadata: ServiceMetadata) -> "ODataQueryBuilder":
        """Set the metadata object to enable more query funtionality like .function_ and query validation."""
        if self._metadata_lock:
           logger.warning("Attempted to change the metadata on this query builder but the metadata lock prevented the change.")
           return self 
        self._metadata = metadata
        return self

    # ------- Target -------- #
    def from_(
        self,
        entity_set: str = None,
        id: Optional[Any] = None
    ) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Target a specific entity-set.
        
        :param entity_set: Entity's entity-set name. Optionally use the logical name (**requires** metadata).
        :type entity_set: str
        :param id: Target a specific record by GUID.
        :type id: Optional[Any]
        """
        self._target = FromTarget.create(entity_set=entity_set, id=id)
        return self

    def function_(self, api_name: str, **params: Any) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Target a specific function (**requires** metadata).

        :param api_name: Name of the function exposed to the API.
        :type api_name: str
        :param params: Set parameter values by {ParamName}=, _{ParamName}=, or _{paramname}=. Optionally, set function parameters using the .params_ query part.
        :type params: Any
        """
        # if no metadata, we can't resolve aliases safely, so keep as-is.
        if self._metadata is None:
            self._target = FunctionTarget.create(api_name, **params)
            return self
        
        fn = self._metadata.function_for_api(api_name)
        
        normalized: dict[str, object] = {}
        for k, v in params.items():
            real = fn.resolve_param_name(k)
            if real is None:
                # raise issue immediately since metadata is present.
                raise TypeError(
                    f"Unknown parameter {k!r} for function {fn.api_name!r}. "
                    f"Valid: {', '.join(sorted(fn.public_param_names()))}"
                )
            if real in normalized:
                raise TypeError(f"Parameter provided more than once (after normalization): {k!r} -> {real!r}")
            normalized[real] = v

        self._target = FunctionTarget.create(api_name=api_name, **normalized)
        return self
    
    @property
    def params_(self) -> FunctionParamsBuilder:
        """
        #### Query Part:
         -Alternate method of setting function parameter values
         -Only needs to be called once per query unless the .done_ Query Part was called
        """
        if not isinstance(self._target, FunctionTarget):
            raise AttributeError("params is only available for FunctionTarget queries")
        if not self._metadata:
            raise AttributeError("params requires metadata to provide hints")
        fn = self._metadata.function_for_api(self._target.api_name)
        return FunctionParamsBuilder(self, fn)

    def entitydefinitions_(
        self,
        entity_id: Optional[Any] = None
    ) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Target the hard-coded /EntityDefinitions enpoint.
         -Does **NOT** support any other query parts.
        #### For query part support:
         -Use .function_("EntityDefinitions") with metadata.

        :param entity_id: Target a specific entity by GUID or logical name.
        :type entity_id: Optional[Any]
        """
        self._target = EntityDefinitionsTarget.create(entity_id=entity_id)
        return self
    
    def edmx_(self) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Target the hard-coded /$Metadata enpoint.
         -Does **NOT** support any other query parts.
        """
        self._target = EdmxTarget.create()
        return self
    
    def whoami_(self) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Target the hard-coded /WhoAmI enpoint.
         -Does **NOT** support any other query parts.
         -For query part support, use .function_("WhoAmI") with metadata.
        """
        self._target = WhoAmITarget.create()
        return self

    # ------- Select -------- #
    def select_(self, *fields: str) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Select specific properties from an entity-set.
         -Duplicate values will be removed.
         -Order **NOT** guaranteed
        
        :param fields: Pass one/multiple field names or Lists/Sets/Tuples of field names. 
        :type fields: str
        """
        normalized = flatten_fields(*fields) # Flatten iterable containers or raw parameters into a deduplicated list.
        for f in normalized:
            if f not in self._select:
                self._select.append(f)
        return self

    # ------- Criteria -------- #
    def where_(self, *items: Any) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Apply a variety of Expressions to curtail the resulting records.
         -Expressions are combined using **AND** if not explicitly stated.
        #### Can use: 
         -And(), Or(), Not(), Eq(), Ne(), Gt(), Ge(), Lt(), Le(), In_()
         -Contains(), StartsWith(), EndsWith()
         -& [and], | [or], ~ [not]
         -Prop().startswith(), Prop().endswith(), Prop().contains(), Prop().in_
         -[Prop()|Literal()] {>, >=, ==, !=, <=, <} [Prop()|Literal()]
        ##### See documentation for more details.
        """
        exprs = flatten_exprs(*items)
        if not exprs:
            return self

        incoming: Expr = And(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else And(self._filter, incoming)
        return self

    def or_where_(self, *items: Any) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Apply a variety of Expressions to curtail the resulting records.
         -Expressions are combined using **OR** if not explicitly stated.
        #### Can use: 
         -And(), Or(), Not(), Eq(), Ne(), Gt(), Ge(), Lt(), Le(), In_()
         -Contains(), StartsWith(), EndsWith()
         -& [and], | [or], ~ [not]
         -Prop().startswith(), Prop().endswith(), Prop().contains(), Prop().in_
         -[Prop()|Literal()] {>, >=, ==, !=, <=, <} [Prop()|Literal()]
        ##### See documentation for more details.
        """
        exprs = flatten_exprs(*items)
        if not exprs:
            return self

        incoming: Expr = Or(*exprs) if len(exprs) > 1 else exprs[0]
        self._filter = incoming if self._filter is None else Or(self._filter, incoming)
        return self

    # ------- Aggregate -------- #
    def count_(self, enabled: bool = True) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Get a count of records expected to be returned by the query.
        """
        self._count = bool(enabled)
        return self

    # ------- Order -------- #
    def orderby_(self, *items: Any) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Order records by a property in (asc)ending or (desc)ending order.
         -Default ordering is decending.
        """
        normalized = flatten_orderby(*items)
        seen = {(i.field, i.desc) for i in self._orderby}
        for it in normalized:
            key = (it.field, it.desc)
            if key not in seen:
                seen.add(key)
                self._orderby.append(it)
        return self

    # ------- Misc -------- #
    def skip_(self, n: int) -> "ODataQueryBuilder":
        if not isinstance(n, int) or n < 0:
            raise ValueError("$skip must be a non-negative integer")
        self._skip = n
        return self

    def top_(self, n: int) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Return only n-records at most.
        """
        if not isinstance(n, int) or n < 0:
            raise ValueError("$top must be a non-negative integer")
        self._top = n
        return self
    
    # ------- Expand -------- #
    def expand_(self, nav: str, query: Optional[ExpandQuery] = None) -> "ODataQueryBuilder":
        """
        #### Query Part:
         -Add a $expand clause.
         -Joins to an associated table.
         -ExpandQueries can have their own set of query parts.

        #### Usage Example:
            q.expand_("primarycontactid", ExpandQuery().select_("fullname").top_(1))
        """
        self._expand.append(ExpandItem(nav=nav, query=query))
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
        if self._expand:
            present.add(QueryPart.EXPAND)
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
            validate_target(self, self._metadata)

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
        if self._expand:
            parts.append("$expand=" + compile_expand(self._expand))


        base = self._target.to_path()
        return base + (("?" + "&".join(parts)) if parts else "")