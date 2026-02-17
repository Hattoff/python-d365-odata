from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Tuple
import re
from .flatten import flatten_exprs

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?\d+\.\d+$")

class Expr:
    """Marker base class for all AST nodes."""
    __slots__ = ()
    pass

    def __and__(self, other: Any) -> "And":
        return And(self, other)

    def __or__(self, other: Any) -> "Or":
        return Or(self, other)

    def __invert__(self) -> "Not":
        return Not(self)

@dataclass(frozen=True)
class Prop(Expr):
    """Property of entity or name of an attribute"""
    name: str

    # comparisons
    def __eq__(self, other: Any) -> "Eq":   # type: ignore[override]
        return Eq(self, other)

    def __ne__(self, other: Any) -> "Ne":   # type: ignore[override]
        return Ne(self, other)

    def __gt__(self, other: Any) -> "Gt":
        return Gt(self, other)

    def __ge__(self, other: Any) -> "Ge":
        return Ge(self, other)

    def __lt__(self, other: Any) -> "Lt":
        return Lt(self, other)

    def __le__(self, other: Any) -> "Le":
        return Le(self, other)

    # string funcs
    def contains(self, needle: Any) -> "Contains":
        return Contains(self, needle)

    def startswith(self, prefix: Any) -> "StartsWith":
        return StartsWith(self, prefix)

    def endswith(self, suffix: Any) -> "EndsWith":
        return EndsWith(self, suffix)
    
    def in_(self, *values: Any) -> "In_":
        return In_(self, *values)


@dataclass(frozen=True)
class Literal(Expr):
    """Literal value will be wrapped in 'single quotes'"""
    value: Any

def _as_expr_left(x: Any) -> Expr:
    if isinstance(x, Expr):
        return x
    if isinstance(x, str):
        return Prop(x)
    return Literal(x)

def _as_expr_right(x: Any) -> Expr:
    if isinstance(x, Expr):
        return x
    return Literal(x)

def _coerce_left_default(x: Any) -> Expr:
    # default: string => Prop, everything else => Literal (unless already Expr)
    if isinstance(x, Expr):
        return x
    if isinstance(x, str):
        return Prop(x)
    return Literal(x)

def _coerce_right_default(x: Any) -> Expr:
    # default: everything => Literal (unless already Expr)
    if isinstance(x, Expr):
        return x
    return Literal(x)


## Note: this is likely not necessary, but I will leave it here for now.
def _coerce_literal_numeric(x: Any) -> Expr:
    if isinstance(x, Expr):
        return x
    if isinstance(x, str):
        s = x.strip()
        if _INT_RE.match(s):
            return Literal(int(s))
        if _FLOAT_RE.match(s):
            return Literal(float(s))
    return Literal(x)


@dataclass(frozen=True, init=False)
class _CoercingBinary(Expr):
    left: Expr
    right: Expr

    # allow subclasses to override these coercers
    @classmethod
    def coerce_left(cls, x: Any) -> Expr:
        return _coerce_left_default(x)

    @classmethod
    def coerce_right(cls, x: Any) -> Expr:
        return _coerce_right_default(x)

    def __init__(self, left: Any, right: Any):
        object.__setattr__(self, "left", type(self).coerce_left(left))
        object.__setattr__(self, "right", type(self).coerce_right(right))


@dataclass(frozen=True, init=False)
class _StrictBinary(Expr):
    left: Expr
    right: Expr
    def __init__(self, left: Expr, right: Expr):
        # runtime safety: fail fast if someone passes non-Expr
        if not isinstance(left, Expr) or not isinstance(right, Expr):
            raise TypeError(
                f"{type(self).__name__} requires Expr on both sides. "
                f"Got left={type(left).__name__}, right={type(right).__name__}"
            )
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)

@dataclass(frozen=True)
class And(Expr):
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
class Or(Expr):
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

@dataclass(frozen=True, init=False)
class In_(Expr):
    left: Expr
    options: Tuple[Expr, ...]

    def __init__(self, left: Any, *options: Any):
        # Allow In_(P("id"), 1, 2) or In_("id", 1, 2)
        object.__setattr__(self, "left", _as_expr_left(left))

        # Support passing a single iterable as options: In_("id", [1,2,3])
        if len(options) == 1 and not isinstance(options[0], (str, bytes)) and hasattr(options[0], "__iter__"):
            raw = list(options[0])
        else:
            raw = list(options)

        coerced = tuple(_as_expr_right(v) for v in raw)
        object.__setattr__(self, "options", coerced)


@dataclass(frozen=True)
class Not(Expr):
    expr: Expr

# Comparison predicates
@dataclass(frozen=True, init=False)
class Eq(_CoercingBinary):
    pass


@dataclass(frozen=True, init=False)
class Ne(_CoercingBinary):
    pass


@dataclass(frozen=True, init=False)
class Gt(_CoercingBinary):
    pass


@dataclass(frozen=True, init=False)
class Ge(_CoercingBinary):
    pass


@dataclass(frozen=True, init=False)
class Lt(_CoercingBinary):
    pass


@dataclass(frozen=True, init=False)
class Le(_CoercingBinary):
    pass

# String functions
@dataclass(frozen=True, init=False)
class Contains(_CoercingBinary):
    @property
    def haystack(self) -> Expr:
        """haystack: left"""
        return self.left
    
    @property
    def needle(self) -> Expr:
        """needle: right"""
        return self.right

@dataclass(frozen=True, init=False)
class StartsWith(_CoercingBinary):
    @property
    def text(self) -> Expr:
        """text: left"""
        return self.left
    
    @property
    def prefix(self) -> Expr:
        """prefix: right"""
        return self.right

@dataclass(frozen=True, init=False)
class EndsWith(_CoercingBinary):
    @property
    def text(self) -> Expr:
        """text: left"""
        return self.left
    
    @property
    def suffix(self) -> Expr:
        """suffix: right"""
        return self.right

# ------- Convenience builders to quickly denote properties or literals -------- #

def P(name: str) -> Prop:
    return Prop(name)

def L(value: Any) -> Literal:
    return Literal(value)