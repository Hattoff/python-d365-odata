from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderByItem:
    field: str
    desc: bool = False
    """False => asc, True => desc"""