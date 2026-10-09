"""Thompson's construction from a parsed regex (spec §7.1, CLAUDE.md C10)."""

from itertools import pairwise
from typing import assert_never

from nfa_studio.compile.atoms import Builder
from nfa_studio.compile.regex_parser import Alt, Cat, Eps, RegexNode, Rep, Sym, render
from nfa_studio.core.model import EPS, Automaton


def thompson(node: RegexNode, alphabet: tuple[str, ...]) -> Automaton:
    """ε-NFA with one start and one accepting state per fragment.

    Concatenation joins fragments by ε; union, star, plus and option add a fresh
    start and end joined by ε. Every state's meaning names its sub-expression:
    "inside <subexpr>: start" or "…: end". Size is O(|expr|).
    """
    b = Builder(alphabet)
    start, end = _fragment(b, node)
    return b.build(start, [end])


def _fragment(b: Builder, node: RegexNode) -> tuple[str, str]:
    text = render(node)
    match node:
        case Sym(symbol):
            start, end = b.state(f"inside {text}: start"), b.state(f"inside {text}: end")
            b.edge(start, symbol, end)
        case Eps():
            start, end = b.state(f"inside {text}: start"), b.state(f"inside {text}: end")
            b.edge(start, EPS, end)
        case Cat(parts):
            pieces = [_fragment(b, part) for part in parts]
            for (_, left_end), (right_start, _) in pairwise(pieces):
                b.edge(left_end, EPS, right_start)
            start, end = pieces[0][0], pieces[-1][1]
        case Alt(options):
            start = b.state(f"inside {text}: start")
            pieces = [_fragment(b, option) for option in options]
            end = b.state(f"inside {text}: end")
            for option_start, option_end in pieces:
                b.edge(start, EPS, option_start)
                b.edge(option_end, EPS, end)
        case Rep(child, op):
            start = b.state(f"inside {text}: start")
            child_start, child_end = _fragment(b, child)
            end = b.state(f"inside {text}: end")
            b.edge(start, EPS, child_start)
            b.edge(child_end, EPS, end)
            if op in ("*", "+"):
                b.edge(child_end, EPS, child_start)
            if op in ("*", "?"):
                b.edge(start, EPS, end)
        case _:
            assert_never(node)
    return start, end
