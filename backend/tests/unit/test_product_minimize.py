import pytest

from nfa_studio.core.determinize import complete, determinize
from nfa_studio.core.minimize import minimize
from nfa_studio.core.model import Automaton
from nfa_studio.core.product import product
from nfa_studio.ir.limits import StateLimitExceeded
from tests.support.machines import ENDS_WITH_AB, accepted_words, machine

STARTS_WITH_A = machine(
    [("s0", "a", "s1"), ("s1", "a", "s1"), ("s1", "b", "s1")],
    start="s0",
    final={"s1"},
    kind="nfa",
    meanings={"s0": "nothing read", "s1": "started with a"},
)


def length_mod(m: int) -> Automaton:
    edges = [(f"r{i}", s, f"r{(i + 1) % m}") for i in range(m) for s in "ab"]
    return machine(edges, start="r0", final={"r0"}, kind="dfa")


def test_product_is_intersection() -> None:
    both = product(STARTS_WITH_A, ENDS_WITH_AB)
    assert accepted_words(both) == accepted_words(STARTS_WITH_A) & accepted_words(ENDS_WITH_AB)
    assert both.kind == "nfa"
    assert both.meanings["q0"] == "A: nothing read · B: scanning (no commitment)"


def test_product_of_dfas_is_a_dfa() -> None:
    assert product(length_mod(2), length_mod(3)).kind == "dfa"
    assert len(product(length_mod(2), length_mod(3)).states) == 6


def test_product_refuses_epsilon_edges() -> None:
    with_eps = machine([("q0", "ε", "q1"), ("q1", "a", "q1")], final={"q1"})
    with pytest.raises(ValueError, match="the right machine has ε edges"):
        product(ENDS_WITH_AB, with_eps)


def test_product_refuses_different_alphabets() -> None:
    other = machine([("q0", "c", "q0")], final={"q0"}, alphabet=("a", "c"))
    with pytest.raises(ValueError, match="alphabets differ"):
        product(ENDS_WITH_AB, other)


def test_product_stops_at_the_state_cap() -> None:
    # 14 and 15 are coprime, so all 210 pairs are reachable.
    with pytest.raises(StateLimitExceeded) as caught:
        product(length_mod(14), length_mod(15))
    assert caught.value.size == 201


def test_minimize_merges_equivalent_states() -> None:
    # A 4-cycle accepting at r0 and r2 is just "even length", which needs 2 states.
    cycle = length_mod(4)
    even_length = Automaton(
        states=cycle.states,
        alphabet=cycle.alphabet,
        delta=cycle.delta,
        start="r0",
        final=frozenset({"r0", "r2"}),
        kind="dfa",
    )
    small = minimize(even_length)
    assert len(small.states) == 2
    assert accepted_words(small) == accepted_words(length_mod(2))


def test_minimize_keeps_minimal_machines_and_their_language() -> None:
    dfa = complete(determinize(ENDS_WITH_AB))
    small = minimize(dfa)
    assert len(small.states) == 3
    assert accepted_words(small) == accepted_words(ENDS_WITH_AB)


def test_minimize_collapses_a_machine_that_accepts_everything() -> None:
    assert minimize(length_mod(1)).states == ("q0",)


def test_minimize_refuses_an_nfa() -> None:
    with pytest.raises(ValueError, match="minimize needs a complete DFA"):
        minimize(ENDS_WITH_AB)
