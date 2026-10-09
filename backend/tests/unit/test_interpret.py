from typing import Any

import pytest

from nfa_studio.compile import compile
from nfa_studio.interpret import interpret
from nfa_studio.interpret.ambiguity import border
from nfa_studio.interpret.nonregular import NonRegularRequest
from nfa_studio.interpret.rule_parser import (
    AlphabetMissing,
    UnsupportedRequest,
    normalize,
    tokenize,
)
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.schema import IRDocument
from nfa_studio.session.clarify import Asking, EditIR, Ready, open_draft
from tests.benchmark.run_benchmark import same_language

LEFT, RIGHT = chr(0x2018), chr(0x2019)
LEFT_DOUBLE, RIGHT_DOUBLE = chr(0x201C), chr(0x201D)


def outcome(text: str) -> Ready | Asking | EditIR:
    return open_draft(interpret(text), text)


def ready(text: str) -> IRDocument:
    result = outcome(text)
    assert isinstance(result, Ready), result
    return result.ir


def spec(language: dict[str, Any], symbols: str) -> IRDocument:
    return validate_ir(
        {"alphabet": {"symbols": list(symbols), "source": "user"}, "language": language}
    )


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("aⁿbⁿ for all n.", "a^nb^n for all n"),
        (f"an {LEFT}even{RIGHT} number of a{RIGHT}s?", "an 'even' number of a's"),
        (f"{LEFT_DOUBLE}ab{RIGHT_DOUBLE}", '"ab"'),
        ("length ≤ 3", "length at most 3"),
        ("  binary   strings\tending in 01 ", "binary strings ending in 01"),
        ("Starts With A", "Starts With A"),
    ],
)
def test_normalize(raw: str, normal: str) -> None:
    assert normalize(raw) == normal


def test_tokenize_lists() -> None:
    assert tokenize("{a, b ,c}") == ["a", "b", "c"]
    assert tokenize("'0' or 10 and \"110\"") == ["0", "10", "110"]


# Wordings the benchmark does not use, so the rules are checked beyond the prompts they
# are scored on (C12: no prompt may be special-cased).
PARAPHRASES: list[tuple[str, dict[str, Any], str]] = [
    ("words over {a,b} beginning with ab", {"type": "starts_with", "pattern": "ab"}, "ab"),
    ("all strings over {0,1} that finish with 10", {"type": "ends_with", "pattern": "10"}, "01"),
    ("strings over {a,b} having aba as a substring", {"type": "contains", "pattern": "aba"}, "ab"),
    (
        "strings over {a,b} where the number of b's is even",
        {"type": "symbol_parity", "symbol": "b", "parity": "even"},
        "ab",
    ),
    (
        "strings over {x,y} with an odd count of x",
        {"type": "symbol_parity", "symbol": "x", "parity": "odd"},
        "xy",
    ),
    (
        "strings over {a,b} containing at least 2 b's",
        {"type": "symbol_count", "symbol": "b", "op": "ge", "n": 2},
        "ab",
    ),
    (
        "binary strings with no more than one 1",
        {"type": "symbol_count", "symbol": "1", "op": "le", "n": 1},
        "01",
    ),
    (
        "strings over {a,b} whose length is a multiple of 5",
        {"type": "length_mod", "m": 5, "r": 0},
        "ab",
    ),
    ("binary strings of length exactly 4", {"type": "regex", "expr": "(0|1)(0|1)(0|1)(0|1)"}, "01"),
    (
        "strings over {a,b} of length at least 2",
        {"type": "regex", "expr": "(a|b)(a|b)(a|b)*"},
        "ab",
    ),
    ("strings over {a,b} that don't contain aa", {"type": "avoids", "pattern": "aa"}, "ab"),
    ("binary strings without 101", {"type": "avoids", "pattern": "101"}, "01"),
    (
        "strings over {a,b} that start with b or end with a",
        {
            "type": "or",
            "children": [
                {"type": "starts_with", "pattern": "b"},
                {"type": "ends_with", "pattern": "a"},
            ],
        },
        "ab",
    ),
    (
        "strings over {0,1} that begin with 0 and contain 11",
        {
            "type": "and",
            "children": [
                {"type": "starts_with", "pattern": "0"},
                {"type": "contains", "pattern": "11"},
            ],
        },
        "01",
    ),
    (
        "strings over {a,b,c} that are one of a, bc, or cab",
        {"type": "literal_set", "words": ["a", "bc", "cab"]},
        "abc",
    ),
    ("strings over {a,b} matching (a|b)*abb", {"type": "regex", "expr": "(a|b)*abb"}, "ab"),
    ("the second symbol is a, over {a,b}", {"type": "regex", "expr": "(a|b)a(a|b)*"}, "ab"),
    ("binary strings whose last symbol is 0", {"type": "ends_with", "pattern": "0"}, "01"),
    (
        "strings over {a,b} in which every b is immediately preceded by a",
        {"type": "regex", "expr": "(a|ab)*"},
        "ab",
    ),
    ("binary strings with no three consecutive 0s", {"type": "avoids", "pattern": "000"}, "01"),
    (
        "strings over {a,b} that have the same first and last letter",
        {"type": "regex", "expr": "a|b|a(a|b)*a|b(a|b)*b"},
        "ab",
    ),
    (
        "strings over {a,b} with exactly one a and ending with b",
        {
            "type": "and",
            "children": [
                {"type": "symbol_count", "symbol": "a", "op": "eq", "n": 1},
                {"type": "ends_with", "pattern": "b"},
            ],
        },
        "ab",
    ),
    (
        "strings over {a,b} that contain ab or ba",
        {
            "type": "or",
            "children": [
                {"type": "contains", "pattern": "ab"},
                {"type": "contains", "pattern": "ba"},
            ],
        },
        "ab",
    ),
    ("strings over {a,b} with even length", {"type": "length_mod", "m": 2, "r": 0}, "ab"),
    (
        "strings over {a,b} with odd length that start with a",
        {
            "type": "and",
            "children": [
                {"type": "length_mod", "m": 2, "r": 1},
                {"type": "starts_with", "pattern": "a"},
            ],
        },
        "ab",
    ),
]


@pytest.mark.parametrize(
    ("text", "language", "symbols"), PARAPHRASES, ids=[p[0] for p in PARAPHRASES]
)
def test_paraphrases_mean_what_they_say(text: str, language: dict[str, Any], symbols: str) -> None:
    assert same_language(spec(language, symbols), ready(text))


def test_paraphrased_questions_and_refusals() -> None:
    asked = outcome("strings over {a,b} with exactly 2 occurrences of aba")
    assert isinstance(asked, Asking) and asked.question.topic == "overlap"
    for text in ("strings with an equal number of 0s and 1s", "strings of the form 0^n1^n"):
        with pytest.raises(NonRegularRequest):
            interpret(text)


@pytest.mark.parametrize(
    ("text", "symbols"),
    [
        ("strings containing 1", ("0", "1")),
        ("strings containing a", ("a", "b")),
        ("strings containing ab", ("a", "b")),
        ("strings containing xy", ("x", "y")),
        ("strings containing x", ("x",)),
        ("strings over {c, a} containing a", ("a", "c")),
        ("binary strings with an even number of 1s", ("0", "1")),
    ],
)
def test_alphabet_inference(text: str, symbols: tuple[str, ...]) -> None:
    """C5: explicit set; binary; only 0/1 or only a/b; the symbols mentioned, plus a partner."""
    ir = ready(text)
    assert ir.alphabet.symbols == symbols
    explicit = "{" in text
    assert ir.alphabet.source == ("user" if explicit else "inferred")
    assert ("alphabet_inferred" in {a.id for a in ir.assumptions}) is not explicit


def test_alphabet_is_asked_when_the_wording_hints_at_more_symbols() -> None:
    asked = outcome("strings over letters that contain ab")
    assert isinstance(asked, Asking)
    assert asked.question.topic == "alphabet"
    assert [o.label for o in asked.question.options] == ["{a, b}", "{a, b, c}", "Edit manually"]


def test_no_symbols_means_no_alphabet() -> None:
    with pytest.raises(AlphabetMissing) as caught:
        interpret("strings of even length")
    assert caught.value.code == "E_ALPHABET_MISSING"


@pytest.mark.parametrize(
    ("pattern", "length"), [("aba", 1), ("aa", 1), ("abab", 2), ("ab", 0), ("a", 0)]
)
def test_border(pattern: str, length: int) -> None:
    assert border(pattern) == length


def test_overlap_is_asked_only_when_the_pattern_can_overlap() -> None:
    """C4: no proper border means the answer cannot change the language."""
    asked = outcome("strings over {a,b} with exactly two occurrences of aba")
    assert isinstance(asked, Asking) and asked.question.topic == "overlap"
    assert asked.question.text == "May the occurrences of aba overlap (as in ababa)?"
    assert "overlap" not in asked.partial_ir["language"]
    ir = ready("strings over {a,b} with exactly two occurrences of ab")
    assert ir.language.model_dump()["overlap"] is False
    assert "no_overlap_possible" in {a.id for a in ir.assumptions}


def test_unqualified_count_is_asked() -> None:
    asked = outcome("strings that contain two a's")
    assert isinstance(asked, Asking)
    assert asked.question.topic == "count_exact_or_at_least"
    assert asked.partial_ir["language"] == {"type": "symbol_count", "symbol": "a", "n": 2}


def test_mixed_and_or_asks_for_the_grouping() -> None:
    asked = outcome("strings over {a,b} that start with a and end with b or contain aa")
    assert isinstance(asked, Asking)
    assert asked.question.topic == "grouping"
    assert [o.label for o in asked.question.options[:2]] == [
        "(start with a and end with b) or contain aa",
        "start with a and (end with b or contain aa)",
    ]
    assert "language" not in asked.partial_ir


def test_a_or_b_followed_by_c_asks_for_the_grouping() -> None:
    asked = outcome("a or b followed by c")
    assert isinstance(asked, Asking) and asked.question.topic == "grouping"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("same number of a's and b's", "equal_counts"),
        ("strings with as many 0s as 1s", "equal_counts"),
        ("aⁿbⁿ for all n", "power_counting"),
        ("a^n b^n c^n", "power_counting"),
        ("palindromes over {0,1}", "palindrome"),
        ("strings of the form ww over {a,b}", "palindrome"),
        ("strings whose length is prime", "length_not_periodic"),
        ("binary strings whose length is a perfect square", "length_not_periodic"),
        ("strings over {a,b} with more a's than b's", "more_than"),
        ("balanced parentheses", "balanced_brackets"),
    ],
)
def test_nonregular_requests_are_refused_with_an_alternative(text: str, reason: str) -> None:
    with pytest.raises(NonRegularRequest) as caught:
        interpret(text)
    assert caught.value.reason == reason
    assert caught.value.alternative.text.startswith("Try")


def test_bounded_alternative_to_anbn_is_a_working_specification() -> None:
    with pytest.raises(NonRegularRequest) as caught:
        interpret("aⁿbⁿ for all n")
    alternative = caught.value.alternative.ir
    assert alternative is not None
    compiled = compile(validate_ir(alternative)).automaton
    assert len(compiled.states) > 1


def test_counts_with_more_than_are_not_mistaken_for_comparisons() -> None:
    assert ready("strings over {a,b} with more than 2 a's").language.model_dump() == {
        "type": "symbol_count",
        "symbol": "a",
        "op": "ge",
        "n": 3,
    }


def test_uninterpretable_text_offers_three_examples() -> None:
    """C11: E_UNSUPPORTED_FEATURE with reason not_interpretable and three example prompts."""
    with pytest.raises(UnsupportedRequest) as caught:
        interpret("strings that are good")
    assert caught.value.code == "E_UNSUPPORTED_FEATURE"
    assert caught.value.reason == "not_interpretable"
    assert len(caught.value.examples) == 3
    for example in caught.value.examples:
        assert isinstance(outcome(example), Ready)


def test_numeric_values_are_outside_the_language() -> None:
    with pytest.raises(UnsupportedRequest) as caught:
        interpret("binary numbers divisible by 3")
    assert caught.value.reason == "numeric_value"


def test_symbols_keep_their_case() -> None:
    ir = ready("strings over {A,b} that start with A")
    assert ir.language.model_dump() == {"type": "starts_with", "pattern": "A"}


def test_confidence_drops_when_a_predicate_is_borrowed() -> None:
    assert interpret("strings over {a,b} ending with ab").confidence == 1.0
    assert interpret("strings over {a,b} ending with ab or ba").confidence == pytest.approx(0.9)
