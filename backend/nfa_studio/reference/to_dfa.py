"""Reference DFA: translate the IR to an extended regex and explore its derivatives (spec §8.1)."""

from collections import deque
from typing import assert_never

from nfa_studio.core.model import Automaton
from nfa_studio.ir.limits import LIMITS, Budget
from nfa_studio.ir.schema import (
    And,
    Avoids,
    Concat,
    Contains,
    EndsWith,
    IRDocument,
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
from nfa_studio.reference.derivatives import Algebra, Re


class NotTranslatable(Exception):
    """The IR uses a node with no reference translation yet (pattern_count, C7)."""


def reference_dfa(doc: IRDocument, budget: Budget | None = None) -> Automaton:
    """Complete DFA whose states are the distinct derivatives of the translated IR.

    Explored breadth-first, symbols in alphabet order; a state accepts when its
    expression is nullable, and ∅ is the dead state. Raises NotTranslatable for
    pattern_count, and StateLimitExceeded or TimeBudgetExceeded past 2,000 states or
    the time budget, so the caller can fall back to V1 and say so.
    """
    budget = budget or Budget(max_states=LIMITS.reference_max_states)
    symbols = doc.alphabet.symbols
    algebra = Algebra()
    start = translate(doc.language, symbols, algebra)
    names = {start: "q0"}
    queue = deque([start])
    delta: dict[tuple[str, str], frozenset[str]] = {}
    while queue:
        budget.check(len(names))
        r = queue.popleft()
        for a in symbols:
            d = algebra.derivative(r, a)
            if d not in names:
                names[d] = f"q{len(names)}"
                budget.check(len(names))
                queue.append(d)
            delta[(names[r], a)] = frozenset({names[d]})
    return Automaton(
        states=tuple(names.values()),
        alphabet=symbols,
        delta=delta,
        start="q0",
        final=frozenset(name for r, name in names.items() if r.nullable),
        kind="dfa",
    )


def translate(node: Node, alphabet: tuple[str, ...], rx: Algebra) -> Re:
    """The C7 translation of an IR node; O stands for Σ∖{s}."""
    sigma = rx.alt(*(rx.sym(a) for a in alphabet))
    anything = rx.star(sigma)

    def others(s: str) -> Re:
        return rx.star(rx.alt(*(rx.sym(a) for a in alphabet if a != s)))

    match node:
        case StartsWith(pattern=p):
            return rx.cat(rx.word(p), anything)
        case EndsWith(pattern=p):
            return rx.cat(anything, rx.word(p))
        case Contains(pattern=p):
            return rx.cat(anything, rx.word(p), anything)
        case Avoids(pattern=p):
            return rx.neg(rx.cat(anything, rx.word(p), anything))
        case SymbolParity(symbol=s, parity=parity):
            o = others(s)
            pairs = rx.star(rx.cat(o, rx.sym(s), o, rx.sym(s)))
            if parity == "even":
                return rx.cat(pairs, o)
            return rx.cat(pairs, o, rx.sym(s), o)
        case SymbolCount(symbol=s, op=op, n=n):
            o = others(s)
            exactly_n = [rx.cat(o, rx.sym(s))] * n
            if op == "eq":
                return rx.cat(*exactly_n, o)
            if op == "ge":
                return rx.cat(*exactly_n, anything)
            return rx.cat(o, *[rx.optional(rx.cat(rx.sym(s), o))] * n)
        case LengthMod(m=m, r=r):
            return rx.cat(rx.star(rx.cat(*[sigma] * m)), *[sigma] * r)
        case LiteralSet(words=words):
            return rx.alt(*(rx.word(w) for w in words))
        case Regex(expr=expr):
            return rx.parse(expr)
        case And(children=children):
            return rx.inter(*(translate(c, alphabet, rx) for c in children))
        case Or(children=children):
            return rx.alt(*(translate(c, alphabet, rx) for c in children))
        case Not(child=child):
            return rx.neg(translate(child, alphabet, rx))
        case Concat(children=children):
            return rx.cat(*(translate(c, alphabet, rx) for c in children))
        case Star(child=child):
            return rx.star(translate(child, alphabet, rx))
        case PatternCount():
            raise NotTranslatable("pattern_count has no reference translation yet (C7)")
        case _:
            assert_never(node)
