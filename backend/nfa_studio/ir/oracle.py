"""Semantic oracle: decides membership straight from the IR, building no automaton (spec §8.1)."""

import re
from functools import cache
from typing import assert_never

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


def matches(node: Node, word: str) -> bool:
    """True if `word` (over the document's alphabet) is in the language of `node`."""
    match node:
        case StartsWith(pattern=p):
            return word.startswith(p)
        case EndsWith(pattern=p):
            return word.endswith(p)
        case Contains(pattern=p):
            return p in word
        case Avoids(pattern=p):
            return p not in word
        case SymbolCount(symbol=s, op=op, n=n):
            return _compare(word.count(s), op, n)
        case SymbolParity(symbol=s, parity=parity):
            return (word.count(s) % 2 == 0) == (parity == "even")
        case LengthMod(m=m, r=r):
            return len(word) % m == r
        case PatternCount(pattern=p, op=op, n=n, overlap=overlap):
            return _compare(count_occurrences(word, p, overlap), op, n)
        case Regex(expr=expr):
            return _python_regex(expr).fullmatch(word) is not None
        case LiteralSet(words=words):
            return word in words
        case And(children=children):
            return all(matches(child, word) for child in children)
        case Or(children=children):
            return any(matches(child, word) for child in children)
        case Not(child=child):
            return not matches(child, word)
        case Concat(children=children):
            return _matches_concat(children, word)
        case Star(child=child):
            return _matches_star(child, word)
        case _:
            assert_never(node)


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


def _matches_concat(children: tuple[Node, ...], word: str) -> bool:
    ends = {0}
    for child in children:
        ends = {j for i in ends for j in range(i, len(word) + 1) if matches(child, word[i:j])}
    return len(word) in ends


def _matches_star(child: Node, word: str) -> bool:
    # split[j] is True when word[:j] is a concatenation of non-empty words of the child.
    split = [True] + [False] * len(word)
    for j in range(1, len(word) + 1):
        split[j] = any(split[i] and matches(child, word[i:j]) for i in range(j))
    return split[len(word)]


@cache
def _python_regex(expr: str) -> re.Pattern[str]:
    """Translate C6 syntax to Python `re`.

    Every operand of `*`, `+` and `?` is wrapped in its own group: Python reads `a*+`
    as possessive and `a*?` as lazy, but in C6 they are (a*)+ and (a*)?. `()` and `ε`
    become an empty group. Symbols are escaped. This is not shared with the compiler's
    parser (C6), so a parser bug cannot hide itself.
    """
    levels: list[list[str]] = [[]]
    for c in expr:
        if c == "(":
            levels.append([])
        elif c == ")":
            if len(levels) == 1:
                raise ValueError(f"unbalanced ')' in regex {expr!r}")
            inner = "".join(levels.pop())
            levels[-1].append(f"(?:{inner})")
        elif c in "*+?":
            if not levels[-1] or levels[-1][-1] == "|":
                raise ValueError(f"{c!r} has no operand in regex {expr!r}")
            levels[-1].append(f"(?:{levels[-1].pop()}){c}")
        elif c == "|":
            levels[-1].append("|")
        elif c == EPS_LABEL:
            levels[-1].append("(?:)")
        else:
            levels[-1].append(re.escape(c))
    if len(levels) != 1:
        raise ValueError(f"unbalanced '(' in regex {expr!r}")
    return re.compile("".join(levels[0]))
