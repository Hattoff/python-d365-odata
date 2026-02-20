from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List

from .metadata import ServiceMetadata
from .types import OrderByItem, QueryPart
from .expand import ExpandItem, ExpandQuery
from .ast import Expr, And, Or
from .compiler import compile_expr, compile_orderby, compile_expand
from .validator import query_validation, target_validation
from .flatten import flatten_fields, flatten_orderby, flatten_exprs
from .targets import Target, FromTarget, EntityDefinitionsTarget, EdmxTarget, WhoAmITarget
from .query import Query

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
    def __init__(self, metadata: Optional[ServiceMetadata] = None, metadata_lock: bool = False):
        self._metadata = metadata
        self._metadata_lock = metadata_lock
        self.main_query = Query(metadata=metadata)

    # Optional way to implement the metadata while building the query.
    def using_(self, metadata: ServiceMetadata) -> "ODataQueryBuilder":
        """Set the metadata object to enable query validation."""
        if self._metadata_lock:
           logger.warning("Attempted to change the metadata on this query builder but the metadata lock prevented the change.")
           return self
        self._metadata = metadata
        return self