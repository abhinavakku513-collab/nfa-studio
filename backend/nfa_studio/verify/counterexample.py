"""Shortest distinguishing word by product BFS on two complete DFAs (spec §8.3)."""

from collections import deque

from nfa_studio.core.model import Automaton, is_complete_dfa
from nfa_studio.ir.limits import Budget


def shortest_counterexample(
    left: Automaton, right: Automaton, budget: Budget | None = None
) -> str | None:
    """The shortest word accepted by exactly one machine, or None if they are equivalent.

    Breadth-first search over reachable state pairs, symbols in alphabet order, stops
    at the first pair whose acceptance differs; BFS order makes the word shortest,
    and among equally short words the first in alphabet order.
    """
    for side, dfa in (("left", left), ("right", right)):
        if not is_complete_dfa(dfa):
            raise ValueError(f"the {side} machine must be a complete DFA")
    if left.alphabet != right.alphabet:
        raise ValueError(f"alphabets differ: {left.alphabet} and {right.alphabet}")

    def target(dfa: Automaton, q: str, a: str) -> str:
        (r,) = dfa.targets(q, a)
        return r

    start = (left.start, right.start)
    parent: dict[tuple[str, str], tuple[tuple[str, str], str] | None] = {start: None}
    queue = deque([start])
    while queue:
        if budget:
            budget.check_time()
        pair = queue.popleft()
        p, q = pair
        if (p in left.final) != (q in right.final):
            return _word_to(pair, parent)
        for a in left.alphabet:
            nxt = (target(left, p, a), target(right, q, a))
            if nxt not in parent:
                parent[nxt] = (pair, a)
                queue.append(nxt)
    return None


def _word_to(
    pair: tuple[str, str], parent: dict[tuple[str, str], tuple[tuple[str, str], str] | None]
) -> str:
    symbols = []
    link = parent[pair]
    while link is not None:
        pair, a = link
        symbols.append(a)
        link = parent[pair]
    return "".join(reversed(symbols))
