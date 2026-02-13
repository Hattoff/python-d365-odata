from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional, Literal

class QueryPart(Enum):
    __ANY__ = auto()
    """Always pass the query part check to allow any parts."""
    __NONE__ = auto()
    """Always fail the query part check restrict any parts."""
    SELECT = auto()
    FILTER = auto()
    ORDERBY = auto()
    SKIP = auto()
    TOP = auto()
    COUNT = auto()
    EXPAND = auto()


@dataclass(frozen=True)
class OrderByItem:
    field: str
    desc: bool = False
    """False => asc, True => desc"""

# ------- Metadata Types -------- #

EdmPrimitive = str  # "Edm.String", "Edm.Guid", etc.

@dataclass(frozen=True)
class FunctionParam:
    name: str
    edm_type: EdmPrimitive
    is_optional: bool = False

@dataclass(frozen=True)
class FunctionDef:
    name: str
    """schema function name (Function Name)"""
    api_name: str
    """callable name on the service (FunctionImport Name or fallback). In case the function is aliased for some reason."""
    params: Dict[str, FunctionParam]
    returns: bool = False
    return_type: Optional[str] = None
