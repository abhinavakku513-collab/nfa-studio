from itertools import count

import pytest

from nfa_studio.core.determinize import complement, complete, determinize, negate, remove_epsilon
from nfa_studio.core.minimize import minimize
from nfa_studio.core.model import DEAD_MEANING, Automaton, has_epsilon, is_complete_dfa
from nfa_studio.ir.limits import Budget, StateLimitExceeded, TimeBudgetExceeded
from tests.support.machines import ENDS_WITH_AB, accepted_words, machine, thompson

CONTAINS_AA = machine(
    [
        ("q0", "a", "q0"),
        ("q0", "b", "q0"),
        ("q0", "a", "q1"),
        ("q1", "a", "q2"),
        ("q2", "a", "q2"),
        ("q2", "b", "q2"),
    ],
    final={"q2"},
    kind="nfa",
)

# (a | ε)* b: a Thompson machine with an ε-cycle through the star.
THOMPSON = thompson(("cat", ("star", ("alt", ("sym", "a"), ("eps",))), ("sym", "b")))


def nth_from_last_is_a(n: int) -> Automaton:
    """The classic NFA whose subset construction has 2^n states."""
    edges = [("q0", "a", "q0"), ("q0", "b", "q0"), ("q0", "a", "p1")]
    edges += [(f"p{i}", s, f"p{i + 1}") for i in range(1, n) for s in "ab"]
    return machine(edges, final={f"p{n}"}, kind="nfa")


def test_remove_epsilon_preserves_the_language() -> None:
    assert has_epsilon(THOMPSON)
    free = remove_epsilon(THOMPSON)
    assert not has_epsilon(free)
    assert free.kind == "nfa"
    assert accepted_words(free) == accepted_words(THOMPSON)


def test_determinize_names_subsets_breadth_first() -> None:
    dfa = determinize(ENDS_WITH_AB)
    assert dfa.kind == "dfa"
    assert dfa.states == ("q0", "q1", "q2")
    assert dict(dfa.delta) == {
        ("q0", "a"): {"q1"},
        ("q0", "b"): {"q0"},
        ("q1", "a"): {"q1"},
        ("q1", "b"): {"q2"},
        ("q2", "a"): {"q1"},
        ("q2", "b"): {"q0"},
    }
    assert dfa.final == {"q2"}
    assert dfa.meanings["q1"] == (
        "one of: scanning (no commitment) | guessed that an a starts the final ab"
    )


def test_determinize_handles_epsilon_machines() -> None:
    assert accepted_words(determinize(THOMPSON)) == accepted_words(THOMPSON)


def test_complete_adds_one_dead_state() -> None:
    dfa = determinize(machine([("q0", "a", "q1")], final={"q1"}))
    assert not is_complete_dfa(dfa)
    full = complete(dfa)
    assert is_complete_dfa(full)
    assert full.states == ("q0", "q1", "q2")
    assert full.dead == {"q2"}
    assert full.meanings["q2"] == DEAD_MEANING
    assert accepted_words(full) == {"a"}


def test_complement_refuses_an_nfa() -> None:
    with pytest.raises(ValueError, match="complement needs a complete DFA, got kind 'nfa'"):
        complement(ENDS_WITH_AB)


def test_complement_refuses_an_incomplete_dfa() -> None:
    dfa = determinize(machine([("q0", "a", "q1")], final={"q1"}))
    with pytest.raises(ValueError, match="with missing transitions"):
        complement(dfa)


def test_swapping_final_states_of_the_nfa_would_be_wrong() -> None:
    # Why the guard exists: the NFA with F swapped still accepts ab, which it should reject.
    swapped = machine(
        [("q0", "a", "q0"), ("q0", "b", "q0"), ("q0", "a", "q1"), ("q1", "b", "q2")],
        final={"q0", "q1"},
    )
    assert "ab" in accepted_words(swapped)
    assert "ab" not in accepted_words(negate(ENDS_WITH_AB))


def test_negate_is_the_complement_relative_to_sigma_star() -> None:
    every_word = accepted_words(machine([("q0", "a", "q0"), ("q0", "b", "q0")], final={"q0"}))
    for auto in (ENDS_WITH_AB, CONTAINS_AA, THOMPSON):
        assert accepted_words(negate(auto)) == every_word - accepted_words(auto)
        assert accepted_words(negate(negate(auto))) == accepted_words(auto)


def test_spec_7_6_not_containing_aa() -> None:
    dfa = minimize(negate(CONTAINS_AA))
    assert dfa.states == ("q0", "q1", "q2")
    assert dict(dfa.delta) == {
        ("q0", "a"): {"q1"},
        ("q0", "b"): {"q0"},
        ("q1", "a"): {"q2"},
        ("q1", "b"): {"q0"},
        ("q2", "a"): {"q2"},
        ("q2", "b"): {"q2"},
    }
    assert dfa.final == {"q0", "q1"}
    assert dfa.dead == {"q2"}


def test_determinize_stops_at_the_state_cap() -> None:
    assert len(determinize(nth_from_last_is_a(7)).states) == 2**7
    with pytest.raises(StateLimitExceeded) as caught:
        determinize(nth_from_last_is_a(8))
    assert caught.value.code == "E_STATE_LIMIT"
    assert caught.value.size == 201


def test_determinize_stops_at_the_time_budget() -> None:
    ticks = count()
    budget = Budget(seconds=5, clock=lambda: float(next(ticks)))
    with pytest.raises(TimeBudgetExceeded) as caught:
        determinize(nth_from_last_is_a(7), budget)
    assert caught.value.code == "E_TIMEOUT"
    # The deadline was hit inside the loop, after some work, not up front.
    assert next(ticks) > 5


def test_negate_shares_the_budget() -> None:
    with pytest.raises(StateLimitExceeded):
        negate(nth_from_last_is_a(8))
