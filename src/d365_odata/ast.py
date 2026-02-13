from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol, Tuple
from .flatten import flatten_exprs

class Expr(Protocol):
    """
    Generic element of a predicate
    """
    pass


@dataclass(frozen=True)
class Prop:
    """
    Property of entity or name of an attribute
    """
    name: str


@dataclass(frozen=True)
class Literal:
    """
    Literal value will be wrapped in 'single quotes'
    """
    value: Any


@dataclass(frozen=True)
class And:
    terms: Tuple[Any, ...]
    """Terms can be AND Expressions or any iterable combination of them."""

    def __init__(self, *terms: Any):
        # Normalize: And(a, And(b,c), d) -> And(a,b,c,d)
        flat = []
        for t in flatten_exprs(*terms):
            if isinstance(t, And):
                flat.extend(t.terms)
            else:
                flat.append(t)
        object.__setattr__(self, "terms", tuple(flat))


@dataclass(frozen=True)
class Or:
    terms: Tuple[Any, ...]
    """Terms can be OR Expressions or any iterable combination of them."""

    def __init__(self, *terms: Any):
        # Normalize: Or(a, Or(b,c), d) -> Or(a,b,c,d)
        flat = []
        for t in flatten_exprs(*terms):
            if isinstance(t, Or):
                flat.extend(t.terms)
            else:
                flat.append(t)
        object.__setattr__(self, "terms", tuple(flat))


@dataclass(frozen=True)
class Not:
    expr: Expr


# Comparison predicates
@dataclass(frozen=True)
class Eq:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Ne:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Gt:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Ge:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Lt:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Le:
    left: Expr
    right: Expr


# String functions
@dataclass(frozen=True)
class Contains:
    left: Expr
    "left: haystack"
    right: Expr
    "right: needle"

    @property
    def haystack(self):
        return self.left
    
    @property
    def needle(self):
        return self.right


@dataclass(frozen=True)
class StartsWith:
    left: Expr
    "left: text"
    right: Expr
    "right: prefix"

    @property
    def text(self):
        return self.left
    
    @property
    def prefix(self):
        return self.right


@dataclass(frozen=True)
class EndsWith:
    left: Expr
    "left: text"
    right: Expr
    "right: suffix"

    @property
    def text(self):
        return self.left
    
    @property
    def suffix(self):
        return self.right


# ------- Convenience builders to quickly denote properties or literals -------- #

def P(name: str) -> Prop:
    return Prop(name)

def L(value: Any) -> Literal:
    return Literal(value)