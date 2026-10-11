"""Descriptions that join conditions with and/or/but not, and the alphabets written around them."""

from typing import Any

import pytest

from nfa_studio.compile import compile
from nfa_studio.core.simulate import accepts
from nfa_studio.interpret import interpret
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.schema import IRDocument
from nfa_studio.session.clarify import Ready, open_draft
from nfa_studio.verify.ladder import verify

CONTAINS_101 = {"type": "contains", "pattern": "101"}
ENDS_00 = {"type": "ends_with", "pattern": "00"}
BOTH = {"type": "and", "children": [CONTAINS_101, ENDS_00]}
EXERCISE = (
    "Construct an NFA over I = {[0,1] accepting every binary string that "
    "contains 101 and end with 00"
)


def ready(text: str) -> IRDocument:
    result = open_draft(interpret(text), text)
    assert isinstance(result, Ready), result
    return result.ir


def language(text: str) -> dict[str, Any]:
    tree: dict[str, Any] = ready(text).language.model_dump(mode="json")
    return tree


def canonical(tree: dict[str, Any]) -> dict[str, Any]:
    """The tree as normalisation orders it, so readings compare by structure."""
    doc = validate_ir(
        {"alphabet": {"symbols": ["0", "1", "a", "b"], "source": "user"}, "language": tree}
    )
    normal: dict[str, Any] = doc.language.model_dump(mode="json")
    return normal


def both(*children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "and", "children": list(children)}


def either(*children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "or", "children": list(children)}


def negated(child: dict[str, Any]) -> dict[str, Any]:
    return {"type": "not", "child": child}


def starts(p: str) -> dict[str, Any]:
    return {"type": "starts_with", "pattern": p}


def ends(p: str) -> dict[str, Any]:
    return {"type": "ends_with", "pattern": p}


def contains(p: str) -> dict[str, Any]:
    return {"type": "contains", "pattern": p}


def test_the_exercise_sentence_reads_as_contains_and_ends_with() -> None:
    ir = ready(EXERCISE)
    assert ir.language.model_dump(mode="json") == canonical(BOTH)
    assert (list(ir.alphabet.symbols), ir.alphabet.source) == (["0", "1"], "user")
    assert ir.assumptions == ()


@pytest.mark.parametrize(
    ("text", "tree"),
    [
        ("binary strings that contain 101 and end with 00", BOTH),
        ("contains 101 or ends with 00", either(CONTAINS_101, ENDS_00)),
        (
            "starts with 1 and contains 00 and ends with 1",
            both(starts("1"), contains("00"), ends("1")),
        ),
        ("contains 101 but does not end with 00", both(CONTAINS_101, negated(ENDS_00))),
        ("strings over {a,b} that contain aba and end with bb", both(contains("aba"), ends("bb"))),
        ("contains 101 as well as ending in 00", BOTH),
        ("has substring 101 and finishes with 00", BOTH),
    ],
)
def test_joined_conditions(text: str, tree: dict[str, Any]) -> None:
    assert language(text) == canonical(tree)


@pytest.mark.parametrize(
    "verb", ["end with", "ends with", "ending with", "ended with", "finish with", "finishes with"]
)
def test_suffix_verbs(verb: str) -> None:
    assert language(f"binary strings that {verb} 00") == ENDS_00


@pytest.mark.parametrize(
    "verb", ["start with", "starts with", "started with", "begin with", "begins with"]
)
def test_prefix_verbs(verb: str) -> None:
    assert language(f"binary strings that {verb} 1") == starts("1")


@pytest.mark.parametrize(
    "verb", ["contain", "contains", "has substring", "having substring", "has the substring"]
)
def test_substring_verbs(verb: str) -> None:
    assert language(f"binary strings that {verb} 101") == CONTAINS_101


@pytest.mark.parametrize("join", ["and", "as well as", "but", "plus"])
def test_conjunctions(join: str) -> None:
    assert language(f"contains 101 {join} ends with 00") == canonical(BOTH)


@pytest.mark.parametrize("join", ["but not", "and not", "and does not", "but does not"])
def test_negated_conjunctions(join: str) -> None:
    assert language(f"contains 101 {join} end with 00") == canonical(
        both(CONTAINS_101, negated(ENDS_00))
    )


@pytest.mark.parametrize(
    ("text", "tree"),
    [
        (
            "starts with 1 and ends with 0 or contains 11",
            either(both(starts("1"), ends("0")), contains("11")),
        ),
        (
            "contains 11 or starts with 1 and ends with 0",
            either(contains("11"), both(starts("1"), ends("0"))),
        ),
        (
            "starts with 0 and ends with 1 or starts with 1 and ends with 0",
            either(both(starts("0"), ends("1")), both(starts("1"), ends("0"))),
        ),
        (
            "starts with 0 or ends with 1 or contains 11",
            either(starts("0"), ends("1"), contains("11")),
        ),
        (
            "starts with 1 and contains 00 but does not end with 1 or contains 111",
            either(both(starts("1"), contains("00"), negated(ends("1"))), contains("111")),
        ),
        # A borrowed predicate stays with the clause it borrows from.
        ("starts with a and ends with b or a", both(starts("a"), either(ends("b"), ends("a")))),
    ],
)
def test_and_binds_tighter_than_or(text: str, tree: dict[str, Any]) -> None:
    assert language(text) == canonical(tree)


@pytest.mark.parametrize(
    "alphabet",
    [
        "over I = {[0,1]",
        "over {0,1",
        "over [0,1]",
        "over Σ = {0,1}",
        "over the alphabet {0, 1}",
        "over 0 and 1",
    ],
)
def test_alphabets_as_typed(alphabet: str) -> None:
    ir = ready(f"strings {alphabet} that contain 101 and end with 00")
    assert (list(ir.alphabet.symbols), ir.alphabet.source) == (["0", "1"], "user")
    assert ir.language.model_dump(mode="json") == canonical(BOTH)


def test_a_named_alphabet_can_open_the_sentence() -> None:
    ir = ready("Σ = {0,1}, strings that contain 101")
    assert (list(ir.alphabet.symbols), ir.alphabet.source) == (["0", "1"], "user")


def test_binary_infers_the_alphabet() -> None:
    ir = ready("binary strings that contain 101 and end with 00")
    assert (list(ir.alphabet.symbols), ir.alphabet.source) == (["0", "1"], "inferred")


def test_listed_symbols_are_read_without_braces() -> None:
    ir = ready("strings over a, b and c that end with c")
    assert list(ir.alphabet.symbols) == ["a", "b", "c"]


@pytest.mark.parametrize(
    "preamble",
    [
        "Construct an NFA over {0,1} accepting every string that",
        "Design a DFA that accepts all strings over {0,1} that",
        "Build an ε-NFA over {0,1} recognising strings that",
        "Construct a finite automaton over {0,1} accepting each binary string that",
    ],
)
def test_exercise_preambles_are_stripped(preamble: str) -> None:
    assert language(f"{preamble} contains 101 and ends with 00") == canonical(BOTH)


ACCEPTED = ["10100", "1010100", "101100", "0010100"]
REJECTED = ["101", "100", "00", "10101", "0000", "1011"]


@pytest.mark.parametrize("text", ["contains 101 and ends with 00", EXERCISE])
def test_contains_101_and_ends_with_00_climbs_the_ladder(text: str) -> None:
    spec = ready(text)
    automaton = compile(spec).automaton
    report = verify(automaton, spec)
    assert [check.level for check in report.checks][:3] == ["V0", "V1", "V2"]
    assert (report.level, report.badge) == ("V2", "green")
    assert [w for w in ACCEPTED if not accepts(automaton, w)] == []
    assert [w for w in REJECTED if accepts(automaton, w)] == []
