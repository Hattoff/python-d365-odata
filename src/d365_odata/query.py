from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, FrozenSet, Any, List, Generic, TypeVar, Self

from .types import OrderByItem, QueryPart
from .ast import Expr, And, Or
from .flatten import flatten_fields, flatten_orderby, flatten_exprs
from .targets import Target, WhoAmITarget, EdmxTarget, EntityDefinitionsTarget, FromTarget, ExpandTarget
from .metadata import ServiceMetadata
from .validator import query_validation, target_validation
from .compiler import compile_expr, compile_orderby, compile_expand

# ------- Queries -------- #

QSelf = TypeVar("QSelf", bound="BaseQuery")

@dataclass
class BaseQuery(Generic[QSelf]):
     # Query options
    _target: Optional[Target] = None
    _select: List[str] = field(default_factory=list)
    _filter: Optional[Expr] = None
    _count: Optional[bool] = None
    _orderby: List[OrderByItem] = field(default_factory=list)
    _skip: Optional[int] = None
    _top: Optional[int] = None
    _expand: List[ExpandQuery] = field(default_factory=list)

    # def __init__(self):
    #     self._target = None
    #     self._select = []
    #     self._filter = None
    #     self._count = None
    #     self._orderby = []
    #     self._skip = None
    #     self._top = None
    #     self._expand = []

    # ------- Select -------- #
    def select_(self, *fields: str) -> QSelf:
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
    def where_(self, *items: Any) -> QSelf:
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

    def or_where_(self, *items: Any) -> QSelf:
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
    def count_(self, enabled: bool = True) -> QSelf:
        """
        #### Query Part:
         -Get a count of records expected to be returned by the query.
        """
        self._count = bool(enabled)
        return self

    # ------- Order -------- #
    def orderby_(self, *items: Any) -> QSelf:
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
    def skip_(self, n: int) -> QSelf:
        if not isinstance(n, int) or n < 0:
            raise ValueError("$skip must be a non-negative integer")
        self._skip = n
        return self

    def top_(self, n: int) -> QSelf:
        """
        #### Query Part:
         -Return only n-records at most.
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
            raise ValueError(f"{target.__class__.__name__} does not allow any query parts.")
        
        disallowed = self._present_parts - set(target.allowed_parts)
        if disallowed:
            names = ", ".join(sorted(p.name for p in disallowed))
            raise ValueError(f"{target.__class__.__name__} does not allow: {names}")

    def generate(self, *, validate: bool = True) -> str:
        raise NotImplementedError()

    def _compile(self, *, validate: Optional[bool] = True, metadata: Optional[ServiceMetadata] = None):
        """
        Compose the query parts into valid syntax.

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
class Query(BaseQuery["Query"]):
    _metadata: ServiceMetadata = None
    # Initialize target
    def from_(
        self,
        entity_set: str,
        *,
        id: Optional[Any] = None,
        focus: Optional[str] = None,
        focus_entity: Optional[str] = None,
    ) -> Query:
        self._target = FromTarget.create(
            entity_set=entity_set, id=id, focus=focus, focus_entity=focus_entity
        )
        return self
    
    def __init__(self, metadata: Optional[ServiceMetadata] = None):
        super().__init__()
        self._metadata = metadata

    def edmx_(self) -> Query:
        self._target = EdmxTarget.create()
        return self

    def whoami_(self) -> Query:
        self._target = WhoAmITarget.create()
        return self
    
    # ------- Expand -------- #
    def expand_(self, navigation_property: str) -> ExpandQuery:
        # """
        # #### Query Part:
        #  -Add a $expand clause.
        #  -Joins to an associated table.
        #  -ExpandQueries can have their own set of query parts.

        # #### Usage Example:
        #     q.expand_("primarycontactid", ExpandQuery().select_("fullname").top_(1))
        # """
        # expanded_query:ExpandQuery = ExpandQuery(nav=nav, parent_query=self)
        # self._expand.append(expanded_query)
        # return expanded_query
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


class ExpandQuery(BaseQuery["ExpandQuery"]):
    _target: Optional[ExpandTarget] = None
    navigation_property: str = ""
    parent: BaseQuery

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

        #### Usage Example:
            q.expand_("primarycontactid", ExpandQuery().select_("fullname").top_(1))
        """
        expand = ExpandQuery(navigation_property=navigation_property, parent=self)
        self._expand.append(expand)
        return expand

    def generate(self, *, validate: bool = True) -> str:
        """
        Crawl back up the query chain and generate from the top -> down.
        Generate from Query will call "_compile" on all child queries.
        """
        return self.parent.generate(validate=validate)

    def _compile(self, *, validate: Optional[bool] = True, metadata: Optional[ServiceMetadata] = None):
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

