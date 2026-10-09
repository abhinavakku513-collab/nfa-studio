from itertools import product as words_over

import pytest

from nfa_studio.core.model import EPS, Automaton
from nfa_studio.core.simulate import (
    InputTooLong,
    SymbolNotInAlphabet,
    accepts,
    simulate,
)
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import EndsWith, Node, Or, Regex, StartsWith, SymbolParity
from tests.support.machines import ENDS_WITH_AB, machine

# spec §7.5: regression fixtures, written out by hand from the specification.
SPEC_TRACES = [
    ("ab", [{"q0"}, {"q0", "q1"}, {"q0", "q2"}], True),
    ("aab", [{"q0"}, {"q0", "q1"}, {"q0", "q1"}, {"q0", "q2"}], True),
    ("bbab", [{"q0"}, {"q0"}, {"q0"}, {"q0", "q1"}, {"q0", "q2"}], True),
    ("aba", [{"q0"}, {"q0", "q1"}, {"q0", "q2"}, {"q0", "q1"}], False),
    ("abb", [{"q0"}, {"q0", "q1"}, {"q0", "q2"}, {"q0"}], False),
    ("a", [{"q0"}, {"q0", "q1"}], False),
    ("", [{"q0"}], False),
]


@pytest.mark.parametrize(("word", "active_sets", "accepted"), SPEC_TRACES)
def test_spec_7_5_traces(word: str, active_sets: list[set[str]], accepted: bool) -> None:
    trace = simulate(ENDS_WITH_AB, word)
    assert [set(s.after) for s in trace.steps] == active_sets
    assert trace.accepted is accepted
    assert accepts(ENDS_WITH_AB, word) is accepted


def test_spec_11_1_witness_for_bbab() -> None:
    trace = simulate(ENDS_WITH_AB, "bbab")
    assert trace.witness == (
        ("q0", "b", "q0"),
        ("q0", "b", "q0"),
        ("q0", "a", "q1"),
        ("q1", "b", "q2"),
    )
    assert [s.moved for s in trace.steps[1:]] == [
        ("q0",),
        ("q0",),
        ("q0", "q1"),
        ("q0", "q2"),
    ]


def test_final_accepted_is_set_only_on_the_last_step() -> None:
    trace = simulate(ENDS_WITH_AB, "abab")
    assert [s.final_accepted for s in trace.steps] == [None, None, None, None, True]
    assert [s.accepting_present for s in trace.steps] == [False, False, True, False, True]


def test_witness_includes_the_closure_of_the_start_state() -> None:
    # Appendix B drops this ε edge and would start the witness at q1 (CLAUDE.md C1).
    auto = machine([("q0", "ε", "q1"), ("q1", "a", "q2")], final={"q2"})
    assert simulate(auto, "a").witness == (("q0", EPS, "q1"), ("q1", "a", "q2"))


def test_trace_records_transitions_and_epsilon_layers() -> None:
    auto = machine(
        [
            ("q0", "ε", "q1"),
            ("q0", "a", "q3"),
            ("q1", "a", "q2"),
            ("q2", "ε", "q3"),
            ("q3", "ε", "q4"),
        ],
        final={"q4"},
    )
    first, second = simulate(auto, "a").steps
    assert first.after == ("q0", "q1")
    assert first.epsilon_layers == ((("q0", EPS, "q1"),),)
    assert second.transitions == (("q0", "a", "q3"), ("q1", "a", "q2"))
    assert second.moved == ("q3", "q2")
    assert second.epsilon_layers == ((("q3", EPS, "q4"),),)
    assert second.after == ("q3", "q2", "q4")
    assert simulate(auto, "a").witness == (("q0", "a", "q3"), ("q3", EPS, "q4"))


def test_empty_input_evaluates_the_start_closure() -> None:
    auto = machine([("q0", "ε", "q1"), ("q1", "a", "q1")], final={"q1"})
    trace = simulate(auto, "")
    assert trace.accepted
    assert trace.steps[0].final_accepted is True
    assert trace.witness == (("q0", EPS, "q1"),)


def test_empty_active_set_stays_empty() -> None:
    auto = machine([("q0", "a", "q1")], final={"q1"})
    trace = simulate(auto, "bab")
    assert [s.after for s in trace.steps] == [("q0",), (), (), ()]
    assert all(s.transitions == () for s in trace.steps[2:])
    assert not trace.accepted
    assert trace.witness is None


def test_witness_can_be_turned_off() -> None:
    assert simulate(ENDS_WITH_AB, "ab", witness=False).witness is None


def test_symbol_outside_the_alphabet_reports_its_position() -> None:
    with pytest.raises(SymbolNotInAlphabet) as caught:
        simulate(ENDS_WITH_AB, "abc")
    assert caught.value.code == "E_SYMBOL_NOT_IN_ALPHABET"
    assert (caught.value.symbol, caught.value.position) == ("c", 3)


def test_input_longer_than_the_limit_is_refused() -> None:
    with pytest.raises(InputTooLong) as caught:
        simulate(ENDS_WITH_AB, "a" * 10_001)
    assert caught.value.code == "E_INPUT_TOO_LONG"
    assert simulate(ENDS_WITH_AB, "a" * 9_999 + "b").accepted


HAND_BUILT: list[tuple[str, Node, Automaton]] = [
    ("ends with ab", EndsWith(pattern="ab"), ENDS_WITH_AB),
    (
        "starts with a or ends with b",
        Or(children=(StartsWith(pattern="a"), EndsWith(pattern="b"))),
        machine(
            [
                ("s", "ε", "a0"),
                ("s", "ε", "b0"),
                ("a0", "a", "a1"),
                ("a1", "a", "a1"),
                ("a1", "b", "a1"),
                ("b0", "a", "b0"),
                ("b0", "b", "b0"),
                ("b0", "b", "b1"),
            ],
            start="s",
            final={"a1", "b1"},
        ),
    ),
    (
        "(ab)* with an ε back edge",
        Regex(expr="(ab)*"),
        machine([("q0", "a", "q1"), ("q1", "b", "q2"), ("q2", "ε", "q0")], final={"q0"}),
    ),
    (
        "even a's with a harmless ε-cycle",
        SymbolParity(symbol="a", parity="even"),
        machine(
            [
                ("e", "a", "o"),
                ("o", "a", "e"),
                ("e", "b", "e"),
                ("o", "b", "o"),
                ("e", "ε", "x"),
                ("x", "ε", "e"),
            ],
            start="e",
            final={"e"},
        ),
    ),
]


@pytest.mark.parametrize(("name", "ir", "auto"), HAND_BUILT, ids=[h[0] for h in HAND_BUILT])
def test_hand_built_machines_agree_with_the_oracle(name: str, ir: Node, auto: Automaton) -> None:
    for n in range(8):
        for letters in words_over("ab", repeat=n):
            word = "".join(letters)
            trace = simulate(auto, word)
            assert trace.accepted == matches(ir, word), (name, word)
