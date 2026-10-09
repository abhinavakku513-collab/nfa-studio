"""Parser for the LSIR regex syntax (CLAUDE.md C6), used only by the production compiler.

Grammar, with postfix binding tighter than concatenation, and concatenation tighter
than union:

    union   := concat ('|' concat)*
    concat  := postfix postfix*
    postfix := atom ('*' | '+' | '?')*
    atom    := symbol | 'ε' | '(' ')' | '(' union ')'

The parser looks one character ahead and never backtracks.
"""

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias, assert_never

from nfa_studio.core.model import EPS_LABEL


class RegexSyntaxError(ValueError):
    def __init__(self, expr: str, position: int, problem: str) -> None:
        super().__init__(f"regex {expr!r}, position {position + 1}: {problem}")
        self.position = position


@dataclass(frozen=True)
class Sym:
    symbol: str


@dataclass(frozen=True)
class Eps:
    pass


@dataclass(frozen=True)
class Cat:
    parts: tuple["RegexNode", ...]


@dataclass(frozen=True)
class Alt:
    options: tuple["RegexNode", ...]


PostfixOp: TypeAlias = Literal["*", "+", "?"]


@dataclass(frozen=True)
class Rep:
    child: "RegexNode"
    op: PostfixOp


RegexNode: TypeAlias = Sym | Eps | Cat | Alt | Rep

_SYNTAX: Final = frozenset("()|*+?")
_POSTFIX: Final[dict[str, PostfixOp]] = {"*": "*", "+": "+", "?": "?"}


def parse_regex(expr: str) -> RegexNode:
    """Parse `expr`; raises RegexSyntaxError with the 0-based position of the problem."""
    parser = _Parser(expr)
    node = parser.union()
    if parser.pos < len(expr):
        raise RegexSyntaxError(expr, parser.pos, "unmatched ')'")
    return node


class _Parser:
    def __init__(self, expr: str) -> None:
        self.expr = expr
        self.pos = 0
        self.depth = 0

    def peek(self) -> str | None:
        return self.expr[self.pos] if self.pos < len(self.expr) else None

    def union(self) -> RegexNode:
        options = [self.concat()]
        while self.peek() == "|":
            self.pos += 1
            options.append(self.concat())
        return options[0] if len(options) == 1 else Alt(tuple(options))

    def concat(self) -> RegexNode:
        parts = []
        while (c := self.peek()) is not None and c not in "|)":
            parts.append(self.postfix())
        if not parts:
            if self.peek() == ")" and self.depth == 0:
                raise RegexSyntaxError(self.expr, self.pos, "unmatched ')'")
            raise RegexSyntaxError(self.expr, self.pos, "empty alternative; write () or ε")
        return parts[0] if len(parts) == 1 else Cat(tuple(parts))

    def postfix(self) -> RegexNode:
        node = self.atom()
        while (op := _POSTFIX.get(self.peek() or "")) is not None:
            self.pos += 1
            node = Rep(node, op)
        return node

    def atom(self) -> RegexNode:
        c = self.peek()
        start = self.pos
        self.pos += 1
        if c == "(":
            if self.peek() == ")":
                self.pos += 1
                return Eps()
            self.depth += 1
            inner = self.union()
            if self.peek() != ")":
                raise RegexSyntaxError(self.expr, start, "'(' is never closed")
            self.depth -= 1
            self.pos += 1
            return inner
        if c == EPS_LABEL:
            return Eps()
        if c is None or c in _SYNTAX:
            raise RegexSyntaxError(self.expr, start, f"{c!r} has nothing to apply to")
        return Sym(c)


def render(node: RegexNode) -> str:
    """Regex text for `node` with only the parentheses that precedence needs."""
    return _render(node, 0)


def _render(node: RegexNode, outer: int) -> str:
    # Precedence: union 0, concatenation 1, postfix 2, atoms 3.
    match node:
        case Sym(symbol):
            return symbol
        case Eps():
            return EPS_LABEL
        case Rep(child, op):
            text, own = _render(child, 3) + op, 2
        case Cat(parts):
            text, own = "".join(_render(p, 2) for p in parts), 1
        case Alt(options):
            text, own = "|".join(_render(o, 1) for o in options), 0
        case _:
            assert_never(node)
    return f"({text})" if own < outer else text
