"""Descriptions typed as commands, wrapped in quotes or brackets, or ending in punctuation."""

from typing import Any

import pytest

from nfa_studio.interpret import interpret
from nfa_studio.interpret.lexicon import EXAMPLE_CATALOG, EXAMPLE_PROMPTS
from nfa_studio.interpret.rule_parser import UnsupportedRequest, tidy
from nfa_studio.session.clarify import Asking, Ready, open_draft

CONTAINS_101 = {"type": "contains", "pattern": "101"}
ENDS_00 = {"type": "ends_with", "pattern": "00"}
ENDS_01 = {"type": "ends_with", "pattern": "01"}
LEFT, RIGHT = chr(0x2018), chr(0x2019)
LEFT_DOUBLE, RIGHT_DOUBLE = chr(0x201C), chr(0x201D)


def read(text: str) -> tuple[list[str], dict[str, Any]]:
    result = open_draft(interpret(text), text)
    assert isinstance(result, Ready), result
    language: dict[str, Any] = result.ir.language.model_dump(mode="json")
    return list(result.ir.alphabet.symbols), language


def test_the_sentence_that_failed_on_the_live_site() -> None:
    symbols, language = read("enter binary strings that contain 101 and end with 00'")
    assert symbols == ["0", "1"]
    assert language == {"type": "and", "children": [CONTAINS_101, ENDS_00]}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"binary strings ending in 01"', ENDS_01),
        ("`binary strings ending in 01`", ENDS_01),
        (f"{LEFT_DOUBLE}binary strings ending in 01{RIGHT_DOUBLE}", ENDS_01),
        (f"{LEFT}binary strings ending in 01{RIGHT}.", ENDS_01),
        ("binary strings ending in 01.", ENDS_01),
        ("binary strings ending in 01;", ENDS_01),
        ("  binary strings ending in 01 : ", ENDS_01),
        ("(binary strings ending in 01)", ENDS_01),
        ("[binary strings ending in 01].", ENDS_01),
        ("Please enter all binary strings that contain 101", CONTAINS_101),
        ("PLEASE ENTER ALL binary strings that contain 101", CONTAINS_101),
        ("give me an NFA for binary strings ending in 01", ENDS_01),
        ("can you construct an NFA for the language of all binary strings ending in 01?", ENDS_01),
        ("I want a DFA that accepts binary strings ending in 01", ENDS_01),
        ("i need an automaton for binary strings ending in 01", ENDS_01),
        ("set of all binary strings containing 101;", CONTAINS_101),
        ("type every binary string that contains 101", CONTAINS_101),
        ("list any binary string that contains 101:", CONTAINS_101),
        ('show me "binary strings ending in 01"', ENDS_01),
        ("generate the language of binary strings ending in 01", ENDS_01),
        ("Write, please, an NFA that recognises binary strings ending in 01", ENDS_01),
    ],
)
def test_command_words_quotes_and_punctuation_are_set_aside(
    text: str, expected: dict[str, Any]
) -> None:
    symbols, language = read(text)
    assert (symbols, language) == (["0", "1"], expected)


def test_an_explicit_alphabet_inside_a_command() -> None:
    symbols, language = read("I want a DFA that accepts strings over {a,b} ending with ab")
    assert (symbols, language) == (["a", "b"], {"type": "ends_with", "pattern": "ab"})


@pytest.mark.parametrize(
    "text",
    [
        "a or b followed by c",
        "every a is immediately followed by b",
        "(ab)*",
        "(a|b)*abb",
        "strings over {a,b} that contain 'ab' twice",
    ],
)
def test_words_that_belong_to_the_description_are_kept(text: str) -> None:
    assert isinstance(open_draft(interpret(text), text), Ready | Asking)


@pytest.mark.parametrize(
    ("raw", "tidied"),
    [
        ('"binary strings ending in 01".', "binary strings ending in 01"),
        ("contains 'ab' twice'", "contains 'ab' twice"),
        ("(ab)*", "(ab)*"),
        ("(ab)", "(ab)"),
        ("(a b) or (b a)", "(a b) or (b a)"),
        ("((strings that start with a))", "strings that start with a"),
    ],
)
def test_tidy(raw: str, tidied: str) -> None:
    assert tidy(raw) == tidied


def refusal(text: str) -> UnsupportedRequest:
    with pytest.raises(UnsupportedRequest) as caught:
        interpret(text)
    assert caught.value.reason == "not_interpretable"
    return caught.value


def test_the_refusal_says_what_was_read_and_what_was_not() -> None:
    error = refusal("binary strings that contain 101 and are pretty")
    assert str(error).startswith(
        'I read the alphabet {0, 1} and "contain 101", but couldn\'t find a condition in '
        '"are pretty".'
    )


def test_the_refusal_suggests_the_closest_example_first() -> None:
    error = refusal("strings whose length is weird")
    assert str(error).startswith('I couldn\'t find a condition in "strings whose length is weird"')
    assert error.examples[0] == "binary strings whose length is divisible by 3"
    assert str(error).endswith(
        "the closest example is 'binary strings whose length is divisible by 3'."
    )
    assert len(error.examples) == 3


def test_with_nothing_in_common_the_usual_example_leads() -> None:
    assert refusal("strings that are good").examples == EXAMPLE_PROMPTS


@pytest.mark.parametrize("example", EXAMPLE_CATALOG)
def test_every_suggestable_example_can_be_read(example: str) -> None:
    assert isinstance(open_draft(interpret(example), example), Ready)
