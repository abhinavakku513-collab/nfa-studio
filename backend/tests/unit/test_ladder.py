from typing import Any

import pytest

from nfa_studio.compile import compile
from nfa_studio.core.model import Automaton
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.schema import IRDocument
from nfa_studio.verify.ladder import (
    NO_REFERENCE_NOTE,
    REFERENCE_LIMIT_NOTE,
    VerificationFailed,
    bounded_length,
    verify,
)
from tests.support.machines import ENDS_WITH_AB, machine


def doc(language: dict[str, Any], symbols: str = "ab") -> IRDocument:
    return validate_ir(
        {"alphabet": {"symbols": list(symbols), "source": "user"}, "language": language}
    )


def compiled(spec: IRDocument) -> Automaton:
    return compile(spec).automaton


@pytest.mark.parametrize(("size", "length"), [(1, 10), (2, 10), (3, 10), (4, 8), (5, 7), (6, 6)])
def test_bounded_length(size: int, length: int) -> None:
    assert bounded_length(size) == length
    assert sum(size**k for k in range(length + 1)) <= 200_000


def test_a_correct_machine_reaches_v2_with_the_spec_evidence() -> None:
    report = verify(ENDS_WITH_AB, doc({"type": "ends_with", "pattern": "ab"}))
    assert (report.level, report.badge) == ("V2", "green")
    assert [(c.level, c.evidence) for c in report.checks] == [
        ("V0", "Well-formed"),
        ("V1", "Verified on all strings up to length 10"),
        ("V2", "Exactly equivalent to reference"),
        ("V3", "Property tests passed (500 runs)"),
    ]
    assert report.notes == ()


def test_closure_laws_add_property_runs() -> None:
    # not → double complement; the regex part keeps ε edges → ε-free view.
    spec = doc(
        {
            "type": "or",
            "children": [
                {"type": "not", "child": {"type": "contains", "pattern": "aa"}},
                {"type": "regex", "expr": "(ab)*"},
            ],
        }
    )
    assert verify(compiled(spec), spec).property_runs == 502


def test_pattern_count_reaches_v1_and_says_why() -> None:
    spec = doc({"type": "pattern_count", "pattern": "aba", "op": "ge", "n": 2, "overlap": True})
    report = verify(compiled(spec), spec)
    assert (report.level, report.badge) == ("V1", "amber")
    assert [c.level for c in report.checks] == ["V0", "V1", "V3"]
    assert report.notes == (NO_REFERENCE_NOTE,)


def test_a_reference_beyond_its_cap_falls_back_to_v1_honestly() -> None:
    spec = doc({"type": "regex", "expr": "(a|b)*a" + "(a|b)" * 11})
    report = verify(compiled(spec), spec)
    assert report.level == "V1"
    assert report.notes[0] == REFERENCE_LIMIT_NOTE


def test_v1_reports_the_shortest_disagreement() -> None:
    with pytest.raises(VerificationFailed) as caught:
        verify(ENDS_WITH_AB, doc({"type": "ends_with", "pattern": "b"}))
    failure = caught.value
    assert failure.code == "E_VERIFY_FAILED"
    assert (failure.level, failure.counterexample) == ("V1", "b")
    assert str(failure) == "V1 failed: the automaton rejects 'b', but the specification accepts it"


def test_v2_catches_a_difference_beyond_the_bounded_length() -> None:
    # Over one symbol, V1 checks lengths 0..10; the two languages first differ at 11.
    spec = doc({"type": "length_mod", "m": 12, "r": 0}, "a")
    wrong = compiled(doc({"type": "length_mod", "m": 11, "r": 0}, "a"))
    with pytest.raises(VerificationFailed) as caught:
        verify(wrong, spec)
    assert (caught.value.level, caught.value.counterexample) == ("V2", "a" * 11)


def test_v3_catches_what_v1_misses_when_there_is_no_reference() -> None:
    # pattern_count has no V2; the machines differ only on a word of length 11.
    def count_a(n: int) -> IRDocument:
        return doc(
            {"type": "pattern_count", "pattern": "a", "op": "ge", "n": n, "overlap": False}, "a"
        )

    with pytest.raises(VerificationFailed) as caught:
        verify(compiled(count_a(12)), count_a(11))
    assert (caught.value.level, caught.value.counterexample) == ("V3", "a" * 11)


def test_v0_refuses_a_machine_over_another_alphabet() -> None:
    other = machine([("q0", "c", "q0")], final={"q0"}, alphabet=("c",))
    with pytest.raises(VerificationFailed, match="V0 failed"):
        verify(other, doc({"type": "contains", "pattern": "a"}))


def test_results_are_cached_per_machine_and_specification() -> None:
    spec = doc({"type": "ends_with", "pattern": "ab"})
    assert verify(ENDS_WITH_AB, spec) is verify(ENDS_WITH_AB, spec)
    # The same machine against another specification is checked afresh, not replayed.
    with pytest.raises(VerificationFailed):
        verify(ENDS_WITH_AB, doc({"type": "ends_with", "pattern": "ba"}))
