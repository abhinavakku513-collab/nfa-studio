import time

import pytest

from nfa_studio.ir.oracle import count_occurrences, matches
from nfa_studio.ir.schema import (
    And,
    Avoids,
    Concat,
    Contains,
    EndsWith,
    LengthMod,
    LiteralSet,
    Node,
    Not,
    Or,
    PatternCount,
    Regex,
    Star,
    StartsWith,
    SymbolCount,
    SymbolParity,
)

CASES: list[tuple[Node, list[str], list[str]]] = [
    (StartsWith(pattern="ab"), ["ab", "abba"], ["", "a", "ba"]),
    (EndsWith(pattern="ab"), ["ab", "bbab"], ["", "aba", "abb"]),
    (Contains(pattern="aa"), ["aa", "baab"], ["", "aba"]),
    (Avoids(pattern="aa"), ["", "aba", "b"], ["aa", "baab"]),
    (SymbolCount(symbol="b", op="eq", n=2), ["bb", "abab"], ["b", "bbb"]),
    (SymbolCount(symbol="b", op="ge", n=2), ["bb", "bbb"], ["", "ab"]),
    (SymbolCount(symbol="b", op="le", n=1), ["", "ab"], ["bb"]),
    (SymbolParity(symbol="a", parity="even"), ["", "aa", "baba"], ["a"]),
    (SymbolParity(symbol="a", parity="odd"), ["a", "abaa"], ["", "aa"]),
    (LengthMod(m=3, r=0), ["", "abb"], ["a", "ab"]),
    (LengthMod(m=2, r=1), ["a", "abb"], ["", "ab"]),
    (LiteralSet(words=("", "ab")), ["", "ab"], ["a", "abab"]),
    (Regex(expr="(ab)*"), ["", "ab", "abab"], ["a", "aba"]),
    (Regex(expr="(b|ab)*"), ["", "b", "ab", "bab"], ["a", "aab", "ba"]),
    (Regex(expr="a*b*"), ["", "aab", "b"], ["ba"]),
    (Regex(expr="()"), [""], ["a"]),
    (Regex(expr="ε|a"), ["", "a"], ["aa"]),
    (Regex(expr="(a|b)?(a|b)?"), ["", "a", "ab"], ["aba"]),
    (
        And(children=(StartsWith(pattern="a"), EndsWith(pattern="b"))),
        ["ab", "aab"],
        ["", "a", "ba"],
    ),
    (Or(children=(Contains(pattern="aa"), EndsWith(pattern="bb"))), ["aa", "abb"], ["ab"]),
    (Not(child=EndsWith(pattern="b")), ["", "a", "ba"], ["b", "ab"]),
    (
        Concat(children=(LiteralSet(words=("a",)), Star(child=LiteralSet(words=("b",))))),
        ["a", "abbb"],
        ["", "b", "aba"],
    ),
    (Star(child=LiteralSet(words=("ab", "b"))), ["", "b", "abab", "bab"], ["a", "aba"]),
]


@pytest.mark.parametrize(("node", "yes", "no"), CASES, ids=[c[0].type for c in CASES])
def test_oracle_on_hand_computed_words(node: Node, yes: list[str], no: list[str]) -> None:
    assert all(matches(node, w) for w in yes)
    assert not any(matches(node, w) for w in no)


@pytest.mark.parametrize(
    ("word", "pattern", "overlapping", "disjoint"),
    [
        ("aaaa", "aa", 3, 2),
        ("ababa", "aba", 2, 1),
        ("abab", "ab", 2, 2),
        ("", "a", 0, 0),
        ("aaa", "aaaa", 0, 0),
    ],
)
def test_pattern_count_semantics(word: str, pattern: str, overlapping: int, disjoint: int) -> None:
    assert count_occurrences(word, pattern, overlap=True) == overlapping
    assert count_occurrences(word, pattern, overlap=False) == disjoint


def test_pattern_count_node_uses_the_overlap_flag() -> None:
    overlapping = PatternCount(pattern="aba", op="ge", n=2, overlap=True)
    assert matches(overlapping, "ababa")
    assert not matches(overlapping.model_copy(update={"overlap": False}), "ababa")


def test_stacked_postfix_operators_keep_their_regex_meaning() -> None:
    # Python would read a*+ as possessive, which could never give back the final a.
    assert matches(Regex(expr="a*+a"), "aa")
    assert matches(Regex(expr="a**"), "aaa")
    assert matches(Regex(expr="a+?"), "")


@pytest.mark.parametrize("expr", ["(a", "a)", "*a", "a|*", "(|+)"])
def test_malformed_regex_is_reported(expr: str) -> None:
    with pytest.raises(ValueError):
        matches(Regex(expr=expr), "a")


@pytest.mark.parametrize("expr", ["(a*)*b", "(a|a)*b", "(a|a|a|a|a|a)*b", "((a*)*)*b"])
def test_ambiguous_repetition_stays_polynomial(expr: str) -> None:
    # A backtracking engine needs about 2^30 to 6^30 steps for these (spec §13).
    started = time.perf_counter()
    assert not matches(Regex(expr=expr), "a" * 30)
    assert time.perf_counter() - started < 2


def test_nested_ir_star_and_concat_stay_polynomial() -> None:
    a = LiteralSet(words=("a",))
    maybe_a = LiteralSet(words=("", "a"))
    nested = Star(child=Concat(children=(Star(child=a), Star(child=Concat(children=(maybe_a, a))))))
    started = time.perf_counter()
    assert not matches(nested, "a" * 30 + "b")
    assert matches(nested, "a" * 30)
    assert time.perf_counter() - started < 2
