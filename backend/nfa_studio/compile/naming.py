"""Deterministic state naming (spec §7.4, CLAUDE.md item 6)."""

from collections import deque

from nfa_studio.core.model import EPS, Automaton, trim


def name_states(auto: Automaton) -> Automaton:
    """Rename states q0, q1, … in breadth-first order from the start state.

    Unreachable states are removed first. At each state, edges are visited by symbol
    in alphabet order, then ε last; within one destination set, states are taken in
    the machine's own state order, which is the construction's creation order. Equal
    IR over an equal alphabet therefore always yields the same names and hash.
    """
    auto = trim(auto)
    names = {auto.start: "q0"}
    queue = deque([auto.start])
    while queue:
        q = queue.popleft()
        for a in (*auto.alphabet, EPS):
            for r in auto.ordered(auto.targets(q, a)):
                if r not in names:
                    names[r] = f"q{len(names)}"
                    queue.append(r)
    return Automaton(
        states=tuple(names.values()),
        alphabet=auto.alphabet,
        delta={
            (names[q], a): frozenset(names[r] for r in dsts) for (q, a), dsts in auto.delta.items()
        },
        start="q0",
        final=frozenset(names[q] for q in auto.final),
        meanings={names[q]: m for q, m in auto.meanings.items()},
        dead=frozenset(names[q] for q in auto.dead),
        kind=auto.kind,
    )
