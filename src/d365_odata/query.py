from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any, List, Self
from .types import OrderByItem, QueryPart
from .ast import Expr, And, Or
from .flatten import flatten_fields, flatten_orderby, flatten_exprs
from .targets import Target, WhoAmITarget, EdmxTarget, EntityDefinitionsTarget, FromTarget, ExpandTarget
from .metadata import ServiceMetadata
from .validator import query_validation
from .compiler import compile_expr, compile_orderby

import logging
logger = logging.getLogger(__name__)

# ------- Query wrapper -------- #
@dataclass(frozen=True)
class D365OData:
    """Wrapper class for ODataQueryBuilder ensures you use the same metadata for each query by locking it."""
    metadata: Optional[ServiceMetadata] = None

    def query(self) -> Query:
        """
        Creates a new Query using the same metadata every time this is called.
        """
        return Query(metadata=self.metadata, metadata_lock=True)

# ------- Queries -------- #

@dataclass
class QueryBase:
    
     # Query options
    _target: Optional[Target] = None
    _select: List[str] = field(default_factory=list)
    _filter: Optional[Expr] = None
    _count: Optional[bool] = None
    _orderby: List[OrderByItem] = field(default_factory=list)
    _skip: Optional[int] = None
    _top: Optional[int] = None
    _expand: List[ExpandQuery] = field(default_factory=list)

    # ------- Select -------- #
    def select_(self, *fields: str) -> Self:
        """
        #### Query Part:
         -Select specific properties from an entity-set.
         -Duplicate values will be removed.
         -Order **NOT** guaranteed

        #### Special Keywords:
         "*" selects all columns on an entity (not specifying a select_ will do the same thing)
         "-" selects the minimum number of columns per entity; usually only one (the primary key) with a few exceptions returning two columns (systemuser)
        
        :param fields: Pass one/multiple field names or Lists/Sets/Tuples of field names. 
        :type fields: str
        """
        normalized = flatten_fields(*fields) # Flatten iterable containers or raw parameters into a deduplicated list.
        for f in normalized:
            if f not in self._select:
                self._select.append(f)
        return self

    # ------- Criteria -------- #
    def where_(self, *items: Any) -> Self:
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

    def or_where_(self, *items: Any) -> Self:
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
    def count_(self, enabled: bool = True) -> Self:
        """
        #### Query Part:
         -Get a count of records expected to be returned by the query.
        """
        self._count = bool(enabled)
        return self

    # ------- Order -------- #
    def orderby_(self, *items: Any) -> Self:
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
    def skip_(self, n: int) -> Self:
        if not isinstance(n, int) or n < 0:
            raise ValueError("$skip must be a non-negative integer")
        self._skip = n
        return self

    def top_(self, n: int) -> Self:
        """
        #### Query Part:
         -Return at most n-records.
        """
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
        if self._expand:
            present.add(QueryPart.EXPAND)
        return present
    
    def _enforce_allowed_parts(self, target: Target) -> None:
        if QueryPart.__ANY__ in target.allowed_parts:
            return
        if self._present_parts and QueryPart.__NONE__ in target.allowed_parts:
            raise ValueError(f"{target.__class__.__name__} does not allow any query parts.{f" {target._part_validation_error}" if target._part_validation_error else ""}")
        
        disallowed = self._present_parts - set(target.allowed_parts)
        if disallowed:
            names = ", ".join(sorted(p.name for p in disallowed))
            raise ValueError(f"{target.__class__.__name__} does not allow: {names}.{f" {target._part_validation_error}" if target._part_validation_error else ""}")

    def generate(self, *, validate: bool = True) -> str:
        """
        Compose the query parts into valid syntax.

        :param validate: Optionally choose to validate this syntax against the metadata provided.
        :type validate: bool
        :return: Return the query string.
        :rtype: str
        """
        raise NotImplementedError()

    def _compile(self, *, validate: Optional[bool] = True, metadata: Optional[ServiceMetadata] = None):
        """
        Used to recursively call on QueryBase classes to compile their query parts. 

        :param validate: Optionally choose to validate this syntax agains the metadata provided.
        :type validate: bool
        :return: Return the query string.
        :rtype: str
        """

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
        return (("&".join(parts)) if parts else "")

@dataclass
class Query(QueryBase):
    _metadata: ServiceMetadata = None
    _metadata_lock: bool = False
    """If True, prevents the metadata from being updated with the using_ function."""

    def __init__(self, metadata: Optional[ServiceMetadata] = None, metadata_lock: Optional[bool] = False):
        super().__init__()
        self._metadata = metadata
        self._metadata_lock = metadata_lock

    # Initialize target
    def from_(
        self,
        entity_set: str,
        *,
        id: Optional[Any] = None,
        focus: Optional[str] = None,
    ) -> Query:
        """
        Indicate the target entity for this query.

        :param id: [Optional] Provide an ID (GUID) of a specifict record.
        :type id: Any
        :param focus: [Optional] Use a Navigation Property to navigate (focus) on a new entity linked to the original target. **Must provide an ID to use.**
        :type focus: Any
        """
        self._target = FromTarget.create(
            entity_set=entity_set, id=id, focus=focus
        )
        return self

    # Optional way to implement the metadata while building the query.
    def using_(self, metadata: ServiceMetadata) -> Query:
        """
        Set the metadata object to enable query validation.
        \n**If metadata lock is set, this function won't do anything.**
        """
        if self._metadata_lock:
           logger.warning("Attempted to change the metadata on this query but the metadata lock prevented the change.")
           return self
        self._metadata = metadata
        return self
    

    def edmx_(self) -> Query:
        """
        Target the /$metadata endpoint.
        \n**This target is hard-coded and will not respond to metadata validation.**
        """
        self._target = EdmxTarget.create()
        return self

    def whoami_(self) -> Query:
        """
        Target the /WhoAmI endpoint.
        \n**This target is hard-coded and will not respond to metadata validation.**
        """
        self._target = WhoAmITarget.create()
        return self
    
    def entitydefinitions_(self) -> Query:
        """
        Target the /EntityDefinitions endpoint.
        \n**This target is hard-coded and will not respond to metadata validation.**
        """
        self._target = EntityDefinitionsTarget.create()
        return self
    
    # ------- Expand -------- #
    def expand_(self, navigation_property: str) -> ExpandQuery:
        """
        #### Query Part:
         -Add a $expand clause.
         -Joins to an associated table.
         -ExpandQueries can have their own set of query parts.
         -Call .done_() to return back to the parent query, or stay in the expanded query context and expand further.
         -Call .done_(True) to return back to the root query.

        #### Usage Example:
            q.expand_("column1") -- Expand to new entity via the column1 navigation property
            q.select_("columnA","columnB","columnC") -- Select from expanded entity
            q._done() -- Return the parent query
        """
        expand = ExpandQuery(navigation_property=navigation_property, parent=self)
        self._expand.append(expand)
        return expand

    def generate(self, *, validate: bool = True) -> str:
        self._enforce_allowed_parts(self._target)

        if validate:
            query_validation(self, metadata=self._metadata)
            for e in self._expand:
                e.validate_query(metadata=self._metadata)

        parts_str = self._compile(validate=validate)
        expansions = []
        if self._expand:
            for e in self._expand:
                exp_str = e._compile(validate=validate, metadata=self._metadata)
                expansions.append(f"$expand={e._target.navigation_property}{(f"({exp_str})" if exp_str else "")}")
        expansions_str = ((",".join(expansions)) if expansions else "")

        if parts_str and expansions_str:
            combined_parts = f"{parts_str}&{expansions_str}"
        else:
            combined_parts = (parts_str or expansions_str)

        base = self._target.to_path()
        return base + (("?" + combined_parts) if combined_parts else "")


class ExpandQuery(QueryBase):
    _target: Optional[ExpandTarget] = None
    navigation_property: str = ""
    parent: QueryBase

    def __init__(self, navigation_property, parent):
        super().__init__()
        self.navigation_property = navigation_property
        self.parent = parent
        self._target = ExpandTarget.create(navigation_property=navigation_property)

    # ------- Expand -------- #
    def expand_(self, navigation_property: str) -> ExpandQuery:
        """
        #### Query Part:
         -Add a $expand clause.
         -Joins to an associated table.
         -ExpandQueries can have their own set of query parts.
         -Call .done_() to return back to the parent query, or stay in the expanded query context and expand further.
         -Call .done_(True) to return back to the root query.

        #### Usage Example:
            q.expand_("column1") -- Expand to new entity via the column1 navigation property
            q.select_("columnA","columnB","columnC") -- Select from expanded entity
            q._done() -- Return the parent query
        """
        expand = ExpandQuery(navigation_property=navigation_property, parent=self)
        self._expand.append(expand)
        return expand

    def generate(self, *, validate: bool = True) -> str:
        # Crawl back up the query chain and generate from the top -> down.
        # Generate from Query will call "_compile" on all child queries.
        return self.parent.generate(validate=validate)

    def _compile(self, *, validate: Optional[bool] = True, metadata: Optional[ServiceMetadata] = None):
        self._enforce_allowed_parts(self._target)
        parts_str = super()._compile(validate=validate, metadata=metadata)
        expansions = []
        if self._expand:
            for e in self._expand:
                exp_str = e._compile(validate=validate, metadata=metadata)
                expansions.append(f"$expand={e._target.navigation_property}{(f"({exp_str})" if exp_str else "")}")
        expansions_str = ((",".join(expansions)) if expansions else "")

        if parts_str and expansions_str:
            combined_parts = f"{parts_str};{expansions_str}"
        else:
            combined_parts = (parts_str or expansions_str)

        return combined_parts

    def validate_query(self, metadata: ServiceMetadata):
        query_validation(self, metadata)
        for e in self._expand:
            e.validate_query(metadata)

    def done_(self, back_to_root: Optional[bool] = False) -> QueryBase:
        """
        Stop configuring this ExpandQuery and return its parent. 
        \nIf back_to_root = True return to the root Query.
        \nUseful if you want to expand multiple columns on the same entity.
        
        :param back_to_root: [Optional] Provide an ID (GUID) of a specifict record.
        :type back_to_root: bool
        :return: Returns the parent of this ExpandQuery. Returns the root Query when back_to_root = True
        :rtype: QueryBase
        """
        if back_to_root:
            if isinstance(self.parent, ExpandQuery):
                return self.parent.done_(back_to_root)
        return self.parent
