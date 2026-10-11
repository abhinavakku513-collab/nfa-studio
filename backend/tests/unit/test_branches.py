import random

import pytest

from nfa_studio.compile import compile
from nfa_studio.compile.branches import branches, label, trace
from nfa_studio.core.model import model_hash
from nfa_studio.core.simulate import accepts
from nfa_studio.interpret import interpret
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.schema import IRDocument
from nfa_studio.session.clarify import Ready, open_draft

AND = "contains 101 and ends with 00"
OR = "contains 101 or ends with 00"
PROMPTS = [
    AND,
    OR,
    "contains 101 but does not end with 00",
    "starts with 1 and contains 00 and ends with 1",
    "starts with 1 and ends with 0 or contains 11",
    "strings over {a,b} that contain aba and end with bb",
    "strings over {a,b} with an even number of a's but not containing bb",
    "strings over {a,b} that start with b or end with a",
    "strings over {a,b,c} that contain ab and do not contain c",
    "binary strings with an odd number of 1s or ending in 00",
]


def ready(text: str) -> IRDocument:
    result = open_draft(interpret(text), text)
    assert isinstance(result, Ready), result
    return result.ir


def test_and_splits_into_one_lane_per_condition() -> None:
    split = branches(ready(AND))
    assert split.combiner == "all"
    assert [b.label for b in split.branches] == ["contain 101", "end with 00"]
    assert [b.negated for b in split.branches] == [False, False]
    assert all(b.automaton.alphabet == ("0", "1") for b in split.branches)


def test_or_combines_with_any() -> None:
    assert branches(ready(OR)).combiner == "any"


def test_a_not_child_is_its_complemented_dfa() -> None:
    split = branches(ready("contains 101 but does not end with 00"))
    lane = split.branches[1]
    assert (lane.label, lane.negated, lane.automaton.kind) == ("NOT end with 00", True, "dfa")
    assert [accepts(lane.automaton, w) for w in ["100", "1001", ""]] == [False, True, True]


def test_a_single_condition_has_no_lanes() -> None:
    split = branches(ready("binary strings ending in 01"))
    assert (split.combiner, split.branches) == (None, ())


def test_a_nested_group_is_one_lane_worded_as_a_whole() -> None:
    split = branches(ready("starts with 1 and ends with 0 or contains 11"))
    assert [b.label for b in split.branches] == ["end with 0 and start with 1", "contain 11"]


def test_lanes_are_built_like_the_main_machine() -> None:
    """Each lane is exactly what compile makes of that condition on its own."""
    doc = ready(AND)
    for lane, child in zip(branches(doc).branches, doc.language.children, strict=True):
        alone = compile(doc.model_copy(update={"language": child})).automaton
        assert model_hash(lane.automaton) == model_hash(alone)


@pytest.mark.parametrize(
    ("word", "lanes", "combined"),
    [("10100", (True, True), True), ("101", (True, False), False), ("10101", (True, False), False)],
)
def test_trace_verdicts(word: str, lanes: tuple[bool, ...], combined: bool) -> None:
    run = trace(branches(ready(AND)), word)
    assert (run.accepted, run.combined) == (lanes, combined)
    assert run.steps[-1].accepting == lanes
    assert run.steps[-1].combined is combined


def test_trace_has_every_lane_at_every_step() -> None:
    run = trace(branches(ready(AND)), "101")
    assert [s.index for s in run.steps] == [0, 1, 2, 3]
    assert [s.symbol for s in run.steps] == [None, "1", "0", "1"]
    assert all(len(s.active) == 2 and len(s.accepting) == 2 for s in run.steps)
    # contains 101 is found on the last symbol, and only then.
    assert [s.accepting[0] for s in run.steps] == [False, False, False, True]


def test_a_single_condition_cannot_be_traced() -> None:
    with pytest.raises(ValueError, match="no branches"):
        trace(branches(ready("binary strings ending in 01")), "01")


@pytest.mark.parametrize("prompt", PROMPTS)
def test_combined_verdict_equals_the_verified_automaton(prompt: str) -> None:
    """500 random words per prompt: the lanes combined decide exactly as the main machine."""
    doc = ready(prompt)
    split = branches(doc)
    assert len(split.branches) >= 2
    main = compile(doc).automaton
    rng = random.Random(prompt)
    symbols = doc.alphabet.symbols
    for _ in range(500):
        word = "".join(rng.choice(symbols) for _ in range(rng.randint(0, 30)))
        assert trace(split, word).combined == accepts(main, word), word


def test_labels_follow_the_confirm_screen() -> None:
    doc = validate_ir(
        {
            "alphabet": {"symbols": ["a", "b"], "source": "user"},
            "language": {
                "type": "or",
                "children": [
                    {"type": "symbol_count", "symbol": "a", "op": "ge", "n": 2},
                    {"type": "symbol_parity", "symbol": "b", "parity": "even"},
                    {"type": "length_mod", "m": 3, "r": 1},
                    {"type": "avoids", "pattern": "bb"},
                    {"type": "literal_set", "words": ["", "ab"]},
                ],
            },
        }
    )
    assert sorted(label(child) for child in doc.language.children) == [
        "are exactly one of ε, ab",
        "contain an even number of b",
        "contain at least 2 occurrences of a",
        "do not contain bb",
        "have a length that leaves remainder 1 when divided by 3",
    ]
