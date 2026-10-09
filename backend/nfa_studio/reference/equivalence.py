"""Exact language comparison of two automata (spec §8.2 V2, CLAUDE.md C12)."""

from nfa_studio.core.determinize import complete, determinize
from nfa_studio.core.model import Automaton, is_complete_dfa
from nfa_studio.ir.limits import LIMITS, Budget
from nfa_studio.verify.counterexample import shortest_counterexample


def language_difference(
    left: Automaton, right: Automaton, budget: Budget | None = None
) -> str | None:
    """The shortest word in exactly one of the two languages, or None if they are equal.

    Each side is determinized and completed first unless it already is a complete
    DFA. The budget caps both at the reference limit of 2,000 states.
    """
    budget = budget or Budget(max_states=LIMITS.reference_max_states)
    return shortest_counterexample(
        _complete_dfa(left, budget), _complete_dfa(right, budget), budget
    )


def _complete_dfa(auto: Automaton, budget: Budget) -> Automaton:
    return auto if is_complete_dfa(auto) else complete(determinize(auto, budget))
