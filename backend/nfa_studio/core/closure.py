"""ε-closure and the step function (spec §4, Appendix B, CLAUDE.md C1, C2)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from weakref import WeakKeyDictionary

from nfa_studio.core.model import EPS, Automaton, Edge

_memo: WeakKeyDictionary[Automaton, dict[str, frozenset[str]]] = WeakKeyDictionary()


def eclose_state(auto: Automaton, q: str) -> frozenset[str]:
    """ECLOSE({q}), memoised per automaton and state."""
    closures = _memo.setdefault(auto, {})
    closure = closures.get(q)
    if closure is None:
        seen = {q}
        stack = [q]
        while stack:
            for r in auto.targets(stack.pop(), EPS):
                if r not in seen:
                    seen.add(r)
                    stack.append(r)
        closure = closures[q] = frozenset(seen)
    return closure


def eclose(auto: Automaton, states: Iterable[str]) -> frozenset[str]:
    """ECLOSE(S): every state reachable from S by zero or more ε edges."""
    return frozenset[str]().union(*(eclose_state(auto, q) for q in states))


def step(auto: Automaton, states: Iterable[str], a: str) -> frozenset[str]:
    """step(S, a) = ECLOSE(⋃_{q ∈ S} δ(q, a))."""
    return eclose(auto, (r for q in states for r in auto.targets(q, a)))


@dataclass(frozen=True)
class Closure:
    states: frozenset[str]
    pred: Mapping[str, tuple[str, str]]
    layers: tuple[tuple[Edge, ...], ...]


def eclose_with_pred(auto: Automaton, states: Iterable[str]) -> Closure:
    """ε-closure by breadth-first search that remembers how each state was first reached.

    `pred[r] = (q, EPS)` for every state r added by the closure; states in the input
    set get no entry. BFS makes every recorded ε chain a shortest one (C1). Frontier
    states and their targets are visited in naming order, so the result is
    deterministic. `layers[d]` holds the ε edges from the states at depth d to the
    states first reached at depth d + 1 (C2).
    """
    frontier = auto.ordered(set(states))
    seen = set(frontier)
    pred: dict[str, tuple[str, str]] = {}
    layers: list[tuple[Edge, ...]] = []
    while frontier:
        layer: list[Edge] = []
        reached: dict[str, None] = {}
        for q in frontier:
            for r in auto.ordered(auto.targets(q, EPS)):
                if r in seen:
                    continue
                layer.append((q, EPS, r))
                if r not in reached:
                    reached[r] = None
                    pred[r] = (q, EPS)
        seen.update(reached)
        if layer:
            layers.append(tuple(layer))
        frontier = auto.ordered(reached)
    return Closure(frozenset(seen), pred, tuple(layers))
