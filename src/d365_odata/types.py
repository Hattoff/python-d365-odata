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