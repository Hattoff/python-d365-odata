from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto

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


@dataclass()
class OrderByItem:
    field: str
    desc: bool = False
    """False => asc, True => desc"""