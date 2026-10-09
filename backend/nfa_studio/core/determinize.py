"""ε-removal, subset construction, completion and complement (spec §4, §7.2, §7.3)."""

from collections import deque
from collections.abc import Iterable
from dataclasses import replace

from nfa_studio.core.closure import eclose, eclose_state, step
from nfa_studio.core.model import (
    DEAD_MEANING,
    Automaton,
    has_epsilon,
    is_complete_dfa,
    trim,
)
from nfa_studio.ir.limits import Budget


def merged_meaning(auto: Automaton, states: Iterable[str]) -> str:
    """Meaning of a state that stands for several states of `auto` (C10)."""
    meanings = list(dict.fromkeys(auto.meaning(q) for q in auto.ordered(states)))
    return meanings[0] if len(meanings) == 1 else "one of: " + " | ".join(meanings)


def remove_epsilon(auto: Automaton) -> Automaton:
    """The ε-free machine with δ′(q, a) = ECLOSE(δ(ECLOSE({q}), a)).

    q accepts in the new machine iff ECLOSE({q}) ∩ F ≠ ∅. States that were reachable
    only through ε edges become unreachable and are trimmed.
    """
    if not has_epsilon(auto):
        return auto
    delta = {
        (q, a): targets
        for q in auto.states
        for a in auto.alphabet
        if (targets := step(auto, eclose_state(auto, q), a))
    }
    final = frozenset(q for q in auto.states if eclose_state(auto, q) & auto.final)
    return trim(replace(auto, delta=delta, final=final, kind="nfa"))


def determinize(auto: Automaton, budget: Budget | None = None) -> Automaton:
    """Subset construction over ε-closed subsets; the result is a DFA without a dead state.

    Subsets are discovered breadth-first, symbols in alphabet order, and named q0, q1, …
    in discovery order (CLAUDE.md item 6). The empty subset is left out; `complete`
    adds it as an explicit dead state.
    """
    budget = budget or Budget()
    start = eclose(auto, (auto.start,))
    names = {start: "q0"}
    queue = deque([start])
    delta: dict[tuple[str, str], frozenset[str]] = {}
    while queue:
        budget.check(len(names))
        subset = queue.popleft()
        for a in auto.alphabet:
            target = step(auto, subset, a)
            if not target:
                continue
            if target not in names:
                names[target] = f"q{len(names)}"
                budget.check(len(names))
                queue.append(target)
            delta[(names[subset], a)] = frozenset({names[target]})
    return trim(
        Automaton(
            states=tuple(names.values()),
            alphabet=auto.alphabet,
            delta=delta,
            start="q0",
            final=frozenset(name for subset, name in names.items() if subset & auto.final),
            meanings={name: merged_meaning(auto, subset) for subset, name in names.items()},
            kind="dfa",
        )
    )


def complete(dfa: Automaton) -> Automaton:
    """Send every missing (state, symbol) pair of a DFA to a fresh dead state."""
    if dfa.kind != "dfa":
        raise ValueError(f"complete needs a DFA, got kind {dfa.kind!r}; determinize first")
    missing = [(q, a) for q in dfa.states for a in dfa.alphabet if not dfa.targets(q, a)]
    if not missing:
        return dfa
    dead = _fresh_state(dfa.states)
    delta = dict(dfa.delta)
    delta.update({key: frozenset({dead}) for key in missing})
    delta.update({(dead, a): frozenset({dead}) for a in dfa.alphabet})
    return trim(
        replace(
            dfa,
            states=(*dfa.states, dead),
            delta=delta,
            meanings={**dfa.meanings, dead: DEAD_MEANING},
        )
    )


def complement(dfa: Automaton) -> Automaton:
    """Swap F and Q∖F of a complete DFA.

    Swapping F on an NFA or on an incomplete DFA gives the wrong language (spec §4),
    so anything else is refused. `negate` builds the complete DFA first.
    """
    if not is_complete_dfa(dfa):
        raise ValueError(
            f"complement needs a complete DFA, got kind {dfa.kind!r}"
            + ("" if dfa.kind != "dfa" else " with missing transitions")
            + "; use negate, which determinizes and completes first"
        )
    return trim(replace(dfa, final=frozenset(dfa.states) - dfa.final))


def negate(auto: Automaton, budget: Budget | None = None) -> Automaton:
    """Complement relative to Σ*: ε-remove → determinize → complete → swap (CLAUDE.md item 7)."""
    budget = budget or Budget()
    dfa = complete(determinize(remove_epsilon(auto), budget))
    budget.check(len(dfa.states))
    return complement(dfa)


def _fresh_state(states: tuple[str, ...]) -> str:
    taken = set(states)
    i = len(states)
    while f"q{i}" in taken:
        i += 1
    return f"q{i}"
