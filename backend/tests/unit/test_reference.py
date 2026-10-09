from itertools import count, product
from typing import Any

import pytest

from nfa_studio.core.model import is_complete_dfa
from nfa_studio.core.simulate import accepts
from nfa_studio.ir.limits import Budget, StateLimitExceeded, TimeBudgetExceeded
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import IRDocument
from nfa_studio.reference.equivalence import language_difference
from nfa_studio.reference.to_dfa import NotTranslatable, reference_dfa
from nfa_studio.verify.counterexample import shortest_counterexample
from tests.support.machines import ENDS_WITH_AB, machine
from tests.unit.test_compile import EVERY_NODE


def doc(language: dict[str, Any], symbols: str = "ab") -> IRDocument:
    return validate_ir(
        {"alphabet": {"symbols": list(symbols), "source": "user"}, "language": language}
    )


TRANSLATABLE = [lang for lang, _, _ in EVERY_NODE if lang["type"] != "pattern_count"]
EXTRA = [
    # Counting translations over three symbols, where O = Σ∖{s} has two symbols.
    ({"type": "symbol_count", "symbol": "b", "op": "le", "n": 2}, "abc"),
    ({"type": "symbol_count", "symbol": "b", "op": "eq", "n": 0}, "abc"),
    ({"type": "symbol_parity", "symbol": "c", "parity": "odd"}, "abc"),
    ({"type": "length_mod", "m": 4, "r": 3}, "abc"),
    # A one-symbol alphabet makes O empty.
    ({"type": "symbol_parity", "symbol": "a", "parity": "even"}, "a"),
    ({"type": "symbol_count", "symbol": "a", "op": "ge", "n": 3}, "a"),
]


@pytest.mark.parametrize(
    ("language", "symbols"),
    [(lang, "ab") for lang in TRANSLATABLE] + EXTRA,
    ids=[lang["type"] for lang in TRANSLATABLE] + [f"{lang['type']}-{s}" for lang, s in EXTRA],
)
def test_reference_dfa_agrees_with_the_oracle(language: dict[str, Any], symbols: str) -> None:
    spec = doc(language, symbols)
    reference = reference_dfa(spec)
    assert is_complete_dfa(reference)
    longest = {1: 12, 2: 7, 3: 5}[len(symbols)]
    for n in range(longest + 1):
        for letters in product(symbols, repeat=n):
            word = "".join(letters)
            assert accepts(reference, word) == matches(spec.language, word), word


def test_pattern_count_is_not_translated() -> None:
    with pytest.raises(NotTranslatable):
        reference_dfa(
            doc({"type": "pattern_count", "pattern": "ab", "op": "eq", "n": 1, "overlap": False})
        )


def test_reference_stops_at_two_thousand_states() -> None:
    # The 12th symbol from the end is a: the minimal DFA has 2^12 states.
    spec = doc({"type": "regex", "expr": "(a|b)*a" + "(a|b)" * 11})
    with pytest.raises(StateLimitExceeded) as caught:
        reference_dfa(spec)
    assert caught.value.size == 2001


def test_reference_stops_at_the_time_budget() -> None:
    ticks = count()
    budget = Budget(max_states=2000, seconds=3, clock=lambda: float(next(ticks)))
    with pytest.raises(TimeBudgetExceeded):
        reference_dfa(doc({"type": "regex", "expr": "(a|b)*a(a|b)(a|b)(a|b)"}), budget)


def test_shortest_counterexample_is_shortest_and_first_in_alphabet_order() -> None:
    # ends with ab vs ends with b: they differ first on "b" (length 1).
    ends_b = reference_dfa(doc({"type": "ends_with", "pattern": "b"}))
    ends_ab = reference_dfa(doc({"type": "ends_with", "pattern": "ab"}))
    assert shortest_counterexample(ends_ab, ends_b) == "b"
    # contains aa vs contains bb: "aa" and "bb" both differ; "aa" comes first.
    has_aa = reference_dfa(doc({"type": "contains", "pattern": "aa"}))
    has_bb = reference_dfa(doc({"type": "contains", "pattern": "bb"}))
    assert shortest_counterexample(has_aa, has_bb) == "aa"


def test_equivalent_machines_have_no_counterexample() -> None:
    reference = reference_dfa(doc({"type": "ends_with", "pattern": "ab"}))
    assert language_difference(ENDS_WITH_AB, reference) is None


def test_empty_word_can_be_the_counterexample() -> None:
    star = reference_dfa(doc({"type": "regex", "expr": "(ab)*"}))
    plus = reference_dfa(doc({"type": "regex", "expr": "(ab)+"}))
    assert shortest_counterexample(star, plus) == ""


def test_counterexample_needs_complete_dfas_over_one_alphabet() -> None:
    reference = reference_dfa(doc({"type": "ends_with", "pattern": "ab"}))
    with pytest.raises(ValueError, match="left machine must be a complete DFA"):
        shortest_counterexample(ENDS_WITH_AB, reference)
    other = machine(
        [("q0", "a", "q0"), ("q0", "c", "q0")], final={"q0"}, alphabet=("a", "c"), kind="dfa"
    )
    with pytest.raises(ValueError, match="alphabets differ"):
        shortest_counterexample(reference, other)


def test_language_difference_determinizes_nfas() -> None:
    reference = reference_dfa(doc({"type": "ends_with", "pattern": "b"}))
    assert language_difference(ENDS_WITH_AB, reference) == "b"
