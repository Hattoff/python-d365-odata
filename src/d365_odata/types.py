from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional, Literal, Set

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

    def resolve_param_name(self, provided: str) -> Optional[str]:
        """
        Map developer-friendly names (e.g. '_{name}', '_{name.lower()}') to the real EDMX param name.
        
        :param provided: Parameter name to check
        :type provided: str
        :return: Actual parameter name or None if not found.
        :rtype: str | None
        """
        if provided in self.params:
            return provided

        if not provided.startswith("_"):
            return None
        
        raw = provided[1:]  # strip leading underscore
        if raw in self.params:
            # is uppercase alias
            return raw

        raw_lower = raw.lower()
        for real in self.params.keys():
            if real.lower() == raw_lower:
                # is lowercase alias
                return real

        return None

    def public_param_names(self) -> Set[str]:
        """python-safe variants of parameter names"""
        out: Set[str] = set()
        for real in self.params.keys():
            out.add(f"_{real}")
            out.add(f"_{real.lower()}")
        return out
