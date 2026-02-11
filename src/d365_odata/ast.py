from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

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

# Logical predicates
@dataclass(frozen=True)
class And:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Or:
    left: Expr
    right: Expr


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


# String functions (string wildcard placement)
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