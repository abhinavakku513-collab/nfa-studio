"""The Branches view: one machine per top-level condition, and a trace across all of them.

This is a visualisation over the same IR. Each child of a top-level and/or is compiled
on its own with the same constructions and alphabet, so the lanes show the parts the
verified product or union is made of. The verified automaton and its ladder are not
touched; `combined` agrees with them by construction, and a test checks it.
"""

from dataclasses import dataclass
from typing import Final, Literal, assert_never

from nfa_studio.compile import compile
from nfa_studio.core.model import Automaton
from nfa_studio.core.simulate import Trace, simulate
from nfa_studio.ir.normalize import normalize
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

Combiner = Literal["all", "any"]

# The confirm screen's wording (frontend Reading.tsx), so a lane reads like its bullet.
OP_WORDS: Final = {"eq": "exactly", "ge": "at least", "le": "at most"}


@dataclass(frozen=True)
class Branch:
    label: str
    node: Node
    automaton: Automaton
    negated: bool


@dataclass(frozen=True)
class Branches:
    """The lanes of a top-level and/or; `combiner` is None and no lanes for one condition."""

    combiner: Combiner | None
    branches: tuple[Branch, ...]


@dataclass(frozen=True)
class BranchStep:
    index: int
    symbol: str | None
    active: tuple[tuple[str, ...], ...]
    accepting: tuple[bool, ...]
    combined: bool


@dataclass(frozen=True)
class BranchTrace:
    word: str
    steps: tuple[BranchStep, ...]
    accepted: tuple[bool, ...]
    combined: bool


def branches(doc: IRDocument) -> Branches:
    """Split `doc` at its top-level and/or; a `not` child is its complemented DFA."""
    doc = normalize(doc)
    language = doc.language
    match language:
        case And(children=children):
            combiner: Combiner = "all"
        case Or(children=children):
            combiner = "any"
        case _:
            return Branches(None, ())
    lanes = tuple(
        Branch(
            label=f"NOT {label(child.child)}" if isinstance(child, Not) else label(child),
            node=child,
            automaton=compile(doc.model_copy(update={"language": child})).automaton,
            negated=isinstance(child, Not),
        )
        for child in children
    )
    return Branches(combiner, lanes)


def combine(combiner: Combiner, verdicts: tuple[bool, ...]) -> bool:
    return all(verdicts) if combiner == "all" else any(verdicts)


def trace(split: Branches, word: str) -> BranchTrace:
    """Run `word` on every lane together: per step, each lane's active set and verdict."""
    if split.combiner is None:
        raise ValueError("a single condition has no branches to trace")
    combiner = split.combiner
    traces: list[Trace] = [simulate(b.automaton, word, witness=False) for b in split.branches]
    steps = tuple(
        BranchStep(
            index=i,
            symbol=traces[0].steps[i].symbol,
            active=tuple(t.steps[i].after for t in traces),
            accepting=(accepting := tuple(t.steps[i].accepting_present for t in traces)),
            combined=combine(combiner, accepting),
        )
        for i in range(len(word) + 1)
    )
    accepted = tuple(t.accepted for t in traces)
    return BranchTrace(word, steps, accepted, combine(combiner, accepted))


def label(node: Node) -> str:
    """What `node` asks of a string, worded as on the confirm screen."""
    match node:
        case StartsWith(pattern=p):
            return f"start with {p}"
        case EndsWith(pattern=p):
            return f"end with {p}"
        case Contains(pattern=p):
            return f"contain {p}"
        case Avoids(pattern=p):
            return f"do not contain {p}"
        case SymbolCount(symbol=s, op=op, n=n):
            return f"contain {OP_WORDS[op]} {n} occurrences of {s}"
        case SymbolParity(symbol=s, parity=parity):
            return f"contain an {parity} number of {s}"
        case LengthMod(m=m, r=r):
            return f"have a length that leaves remainder {r} when divided by {m}"
        case PatternCount(pattern=p, op=op, n=n, overlap=overlap):
            counting = "overlapping allowed" if overlap else "disjoint occurrences"
            return f"contain {p} {OP_WORDS[op]} {n} times, counting {counting}"
        case Regex(expr=expr):
            return f"match the regular expression {expr}"
        case LiteralSet(words=words):
            return f"are exactly one of {', '.join(w or 'ε' for w in words)}"
        case And(children=children):
            return " and ".join(_grouped(child) for child in children)
        case Or(children=children):
            return " or ".join(_grouped(child) for child in children)
        case Not(child=child):
            return f"not {_grouped(child)}"
        case Concat(children=children):
            return "in order, " + "; then ".join(label(child) for child in children)
        case Star(child=child):
            return f"repeat zero or more times: {label(child)}"
        case _:
            assert_never(node)


def _grouped(node: Node) -> str:
    text = label(node)
    return f"({text})" if isinstance(node, And | Or) else text
