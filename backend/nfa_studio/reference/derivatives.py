"""Extended regular expressions with Brzozowski derivatives (spec §8.1, CLAUDE.md C7).

Shares no code with the production compiler: it has its own expression type, its own
regex parser and its own notion of state. Agreement between the two is the evidence.
"""

from dataclasses import dataclass
from typing import Final, Literal

from nfa_studio.core.model import EPS_LABEL

Op = Literal["empty", "eps", "sym", "cat", "alt", "and", "not", "star"]


@dataclass(frozen=True, eq=False)
class Re:
    """An interned expression: within one `Algebra`, equal structure is the same object.

    Identity equality and hashing make derivative memo lookups O(1) instead of
    re-hashing whole trees. `uid` gives the fixed order used to sort | and & children.
    """

    op: Op
    kids: tuple["Re", ...]
    symbol: str
    uid: int
    nullable: bool


class Algebra:
    """Smart constructors, derivatives and the intern table for one exploration.

    The constructors keep every expression in a normal form: ∅ and ε identities,
    | and & flattened, sorted and deduplicated (ACI), ¬¬r = r, r** = r*,
    ε* = ∅* = ε, ∅·r = r·∅ = ∅, and concatenation associated to the right. Brzozowski
    showed that, up to these rules, a regex has finitely many derivatives.
    """

    def __init__(self) -> None:
        self._table: dict[tuple[str, str, tuple[int, ...]], Re] = {}
        self._derivatives: dict[tuple[Re, str], Re] = {}
        self.empty = self._make("empty", (), "", False)
        self.eps = self._make("eps", (), "", True)
        self.top = self._make("not", (self.empty,), "", True)

    def _make(self, op: Op, kids: tuple[Re, ...], symbol: str, nullable: bool) -> Re:
        key = (op, symbol, tuple(k.uid for k in kids))
        node = self._table.get(key)
        if node is None:
            node = self._table[key] = Re(op, kids, symbol, len(self._table), nullable)
        return node

    def sym(self, a: str) -> Re:
        return self._make("sym", (), a, False)

    def word(self, w: str) -> Re:
        return self.cat(*(self.sym(a) for a in w))

    def cat(self, *parts: Re) -> Re:
        result = self.eps
        for part in reversed(parts):
            result = self._cat2(part, result)
        return result

    def _cat2(self, left: Re, right: Re) -> Re:
        if left is self.empty or right is self.empty:
            return self.empty
        if left is self.eps:
            return right
        if right is self.eps:
            return left
        if left.op == "cat":
            return self._cat2(left.kids[0], self._cat2(left.kids[1], right))
        return self._make("cat", (left, right), "", left.nullable and right.nullable)

    def alt(self, *parts: Re) -> Re:
        kids = self._flatten("alt", parts)
        if self.top in kids:
            return self.top
        kids.discard(self.empty)
        return self._nary("alt", kids, self.empty, any(k.nullable for k in kids))

    def inter(self, *parts: Re) -> Re:
        kids = self._flatten("and", parts)
        if self.empty in kids:
            return self.empty
        kids.discard(self.top)
        return self._nary("and", kids, self.top, all(k.nullable for k in kids))

    def _flatten(self, op: Op, parts: tuple[Re, ...]) -> set[Re]:
        kids: set[Re] = set()
        for part in parts:
            kids.update(part.kids if part.op == op else (part,))
        return kids

    def _nary(self, op: Op, kids: set[Re], unit: Re, nullable: bool) -> Re:
        if not kids:
            return unit
        if len(kids) == 1:
            return next(iter(kids))
        return self._make(op, tuple(sorted(kids, key=lambda k: k.uid)), "", nullable)

    def neg(self, r: Re) -> Re:
        if r.op == "not":
            return r.kids[0]
        return self._make("not", (r,), "", not r.nullable)

    def star(self, r: Re) -> Re:
        if r is self.empty or r is self.eps:
            return self.eps
        if r.op == "star":
            return r
        return self._make("star", (r,), "", True)

    def optional(self, r: Re) -> Re:
        return self.alt(r, self.eps)

    def derivative(self, r: Re, a: str) -> Re:
        """The expression for { w | a·w ∈ L(r) }."""
        key = (r, a)
        known = self._derivatives.get(key)
        if known is None:
            known = self._derivatives[key] = self._derive(r, a)
        return known

    def _derive(self, r: Re, a: str) -> Re:
        match r.op:
            case "empty" | "eps":
                return self.empty
            case "sym":
                return self.eps if r.symbol == a else self.empty
            case "cat":
                head, tail = r.kids
                through_head = self.cat(self.derivative(head, a), tail)
                if head.nullable:
                    return self.alt(through_head, self.derivative(tail, a))
                return through_head
            case "alt":
                return self.alt(*(self.derivative(k, a) for k in r.kids))
            case "and":
                return self.inter(*(self.derivative(k, a) for k in r.kids))
            case "not":
                return self.neg(self.derivative(r.kids[0], a))
            case "star":
                return self.cat(self.derivative(r.kids[0], a), r)
        raise ValueError(f"unknown operator {r.op!r}")

    def parse(self, expr: str) -> Re:
        """The reference's own parser for C6 regex syntax; malformed input raises ValueError."""
        return _Parser(self, expr).parse()


_POSTFIX: Final = frozenset("*+?")


class _Parser:
    def __init__(self, algebra: Algebra, expr: str) -> None:
        self.re = algebra
        self.expr = expr
        self.pos = 0

    def parse(self) -> Re:
        result = self.union()
        if self.pos != len(self.expr):
            raise ValueError(f"unmatched ')' at position {self.pos + 1} in {self.expr!r}")
        return result

    def _peek(self) -> str:
        return self.expr[self.pos : self.pos + 1]

    def union(self) -> Re:
        options = [self.concatenation()]
        while self._peek() == "|":
            self.pos += 1
            options.append(self.concatenation())
        return self.re.alt(*options)

    def concatenation(self) -> Re:
        parts = []
        while self._peek() not in ("", "|", ")"):
            parts.append(self.repetition())
        if not parts:
            raise ValueError(f"empty alternative at position {self.pos + 1} in {self.expr!r}")
        return self.re.cat(*parts)

    def repetition(self) -> Re:
        r = self.atom()
        while (op := self._peek()) and op in _POSTFIX:
            self.pos += 1
            if op == "*":
                r = self.re.star(r)
            elif op == "+":
                r = self.re.cat(r, self.re.star(r))
            else:
                r = self.re.optional(r)
        return r

    def atom(self) -> Re:
        c = self._peek()
        self.pos += 1
        if c == "(":
            if self._peek() == ")":
                self.pos += 1
                return self.re.eps
            inner = self.union()
            if self._peek() != ")":
                raise ValueError(f"'(' is never closed in {self.expr!r}")
            self.pos += 1
            return inner
        if c == EPS_LABEL:
            return self.re.eps
        if c in ("", ")", "|") or c in _POSTFIX:
            raise ValueError(f"{c!r} at position {self.pos} has nothing to apply to")
        return self.re.sym(c)
