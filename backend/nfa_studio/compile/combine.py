"""Combinators over compiled children (spec §7.2)."""

from itertools import pairwise

from nfa_studio.compile.atoms import Builder
from nfa_studio.core.determinize import remove_epsilon
from nfa_studio.core.model import EPS, Automaton
from nfa_studio.core.product import product
from nfa_studio.ir.limits import Budget


def union(parts: list[Automaton]) -> Automaton:
    """A new start with an ε edge to each part's start; accepting = the union of theirs."""
    b = Builder(parts[0].alphabet)
    start = b.state("choosing an alternative")
    final: list[str] = []
    for part in parts:
        names = b.embed(part)
        b.edge(start, EPS, names[part.start])
        final.extend(names[q] for q in part.final)
    return b.build(start, final)


def concat(parts: list[Automaton]) -> Automaton:
    """ε from every accepting state of each part to the start of the next."""
    b = Builder(parts[0].alphabet)
    names = [b.embed(part) for part in parts]
    for (left, left_names), (right, right_names) in pairwise(zip(parts, names, strict=True)):
        for q in left.final:
            b.edge(left_names[q], EPS, right_names[right.start])
    return b.build(names[0][parts[0].start], (names[-1][q] for q in parts[-1].final))


def star(part: Automaton) -> Automaton:
    """A new accepting start state, ε into the part and ε back from its accepting states."""
    b = Builder(part.alphabet)
    start = b.state("between repetitions (accepts here)")
    names = b.embed(part)
    b.edge(start, EPS, names[part.start])
    for q in part.final:
        b.edge(names[q], EPS, start)
    return b.build(start, [start])


def intersection(parts: list[Automaton], budget: Budget) -> Automaton:
    """ε-removal on each part, then the product construction, folded left to right."""
    result = remove_epsilon(parts[0])
    for part in parts[1:]:
        result = product(result, remove_epsilon(part), budget)
    return result
