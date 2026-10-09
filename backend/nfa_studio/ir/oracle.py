"""Semantic oracle: decides membership straight from the IR, building no automaton (spec §8.1)."""

from dataclasses import dataclass
from functools import cache
from typing import Final, Literal, TypeAlias, assert_never

from nfa_studio.core.model import EPS_LABEL
from nfa_studio.ir.schema import (
    And,
    Avoids,
    Concat,
    Contains,
    CountOp,
    EndsWith,
    LengthMod,
    LiteralSet,
    Node,
    Not,
    Or,
    PatternCount,
    Regex,
    Star,
    StartsWith,
    SymbolCount,
    SymbolParity,
)

# The oracle's own regex tree, deliberately not shared with the compiler or the
# reference (C6), so a parser bug in one of them cannot hide itself.


@dataclass(frozen=True)
class _Sym:
    symbol: str


@dataclass(frozen=True)
class _Eps:
    pass


@dataclass(frozen=True)
class _Cat:
    parts: tuple["OracleRegex", ...]


@dataclass(frozen=True)
class _Alt:
    options: tuple["OracleRegex", ...]


_RepOp: TypeAlias = Literal["*", "+", "?"]


@dataclass(frozen=True)
class _Rep:
    child: "OracleRegex"
    op: _RepOp


OracleRegex: TypeAlias = _Sym | _Eps | _Cat | _Alt | _Rep

_SYNTAX: Final = frozenset("()|*+?")
_REPEAT: Final[dict[str, _RepOp]] = {"*": "*", "+": "+", "?": "?"}


def matches(node: Node, word: str) -> bool:
    """True if `word` (over the document's alphabet) is in the language of `node`."""
    return _Matcher(word).member(node, 0, len(word))


def count_occurrences(word: str, pattern: str, overlap: bool) -> int:
    """Occurrences of `pattern` in `word` (C3).

    With overlap, every start index counts. Without, the count is the largest number
    of pairwise disjoint occurrences, which a greedy leftmost scan finds.
    """
    if overlap:
        return sum(word.startswith(pattern, i) for i in range(len(word)))
    count = i = 0
    while (j := word.find(pattern, i)) != -1:
        count += 1
        i = j + len(pattern)
    return count


class _Matcher:
    """Membership of every factor word[i:j], memoised for one word.

    Concatenation, star and regex repetition try every split point, so evaluating
    them naively (or with a backtracking engine) is exponential on inputs such as
    (a|a)*b. Memoising each (node, i, j) answer, and for regexes each (node, i) set of
    end positions, bounds the work by O(|tree| · n³).
    """

    def __init__(self, word: str) -> None:
        self.word = word
        self._member: dict[tuple[int, int, int], bool] = {}
        self._ends: dict[tuple[int, int], frozenset[int]] = {}

    def member(self, node: Node, i: int, j: int) -> bool:
        key = (id(node), i, j)
        known = self._member.get(key)
        if known is None:
            known = self._member[key] = self._decide(node, i, j)
        return known

    def _decide(self, node: Node, i: int, j: int) -> bool:
        factor = self.word[i:j]
        match node:
            case StartsWith(pattern=p):
                return factor.startswith(p)
            case EndsWith(pattern=p):
                return factor.endswith(p)
            case Contains(pattern=p):
                return p in factor
            case Avoids(pattern=p):
                return p not in factor
            case SymbolCount(symbol=s, op=op, n=n):
                return _compare(factor.count(s), op, n)
            case SymbolParity(symbol=s, parity=parity):
                return (factor.count(s) % 2 == 0) == (parity == "even")
            case LengthMod(m=m, r=r):
                return (j - i) % m == r
            case PatternCount(pattern=p, op=op, n=n, overlap=overlap):
                return _compare(count_occurrences(factor, p, overlap), op, n)
            case Regex(expr=expr):
                return j in self._regex_ends(parse_oracle_regex(expr), i)
            case LiteralSet(words=words):
                return factor in words
            case And(children=children):
                return all(self.member(child, i, j) for child in children)
            case Or(children=children):
                return any(self.member(child, i, j) for child in children)
            case Not(child=child):
                return not self.member(child, i, j)
            case Concat(children=children):
                ends = {i}
                for child in children:
                    ends = {b for a in ends for b in range(a, j + 1) if self.member(child, a, b)}
                return j in ends
            case Star(child=child):
                reached = [False] * (j - i + 1)
                reached[0] = True
                for b in range(i + 1, j + 1):
                    reached[b - i] = any(
                        reached[a - i] and self.member(child, a, b) for a in range(i, b)
                    )
                return reached[j - i]
            case _:
                assert_never(node)

    def _regex_ends(self, node: OracleRegex, i: int) -> frozenset[int]:
        """Every j such that word[i:j] matches `node`."""
        key = (id(node), i)
        known = self._ends.get(key)
        if known is None:
            known = self._ends[key] = self._regex_step(node, i)
        return known

    def _regex_step(self, node: OracleRegex, i: int) -> frozenset[int]:
        match node:
            case _Sym(symbol):
                return frozenset({i + 1}) if self.word[i : i + 1] == symbol else frozenset()
            case _Eps():
                return frozenset({i})
            case _Cat(parts):
                ends = frozenset({i})
                for part in parts:
                    ends = frozenset(b for a in ends for b in self._regex_ends(part, a))
                return ends
            case _Alt(options):
                return frozenset(b for o in options for b in self._regex_ends(o, i))
            case _Rep(child, "?"):
                return frozenset({i}) | self._regex_ends(child, i)
            case _Rep(child, op):
                first = self._regex_ends(child, i)
                reached = set(first) | ({i} if op == "*" else set())
                frontier = list(first)
                while frontier:
                    for b in self._regex_ends(child, frontier.pop()):
                        if b not in reached:
                            reached.add(b)
                            frontier.append(b)
                return frozenset(reached)
            case _:
                assert_never(node)


def _compare(value: int, op: CountOp, n: int) -> bool:
    match op:
        case "eq":
            return value == n
        case "ge":
            return value >= n
        case "le":
            return value <= n
        case _:
            assert_never(op)


@cache
def parse_oracle_regex(expr: str) -> OracleRegex:
    """The oracle's own parser for C6 syntax; malformed input raises ValueError."""
    tree, pos = _union(expr, 0)
    if pos != len(expr):
        raise ValueError(f"unmatched ')' at position {pos + 1} in regex {expr!r}")
    return tree


def _union(expr: str, pos: int) -> tuple[OracleRegex, int]:
    options: list[OracleRegex] = []
    while True:
        parts: list[OracleRegex] = []
        while pos < len(expr) and expr[pos] not in "|)":
            atom, pos = _atom(expr, pos)
            while (op := _REPEAT.get(expr[pos : pos + 1])) is not None:
                atom, pos = _Rep(atom, op), pos + 1
            parts.append(atom)
        if not parts:
            raise ValueError(f"empty alternative at position {pos + 1} in regex {expr!r}")
        options.append(parts[0] if len(parts) == 1 else _Cat(tuple(parts)))
        if pos < len(expr) and expr[pos] == "|":
            pos += 1
            continue
        return (options[0] if len(options) == 1 else _Alt(tuple(options))), pos


def _atom(expr: str, pos: int) -> tuple[OracleRegex, int]:
    c = expr[pos]
    if c == "(":
        if expr[pos + 1 : pos + 2] == ")":
            return _Eps(), pos + 2
        inner, end = _union(expr, pos + 1)
        if end >= len(expr) or expr[end] != ")":
            raise ValueError(f"'(' at position {pos + 1} is never closed in regex {expr!r}")
        return inner, end + 1
    if c == EPS_LABEL:
        return _Eps(), pos + 1
    if c in _SYNTAX:
        raise ValueError(f"{c!r} at position {pos + 1} has nothing to apply to in {expr!r}")
    return _Sym(c), pos + 1
