"""Many phrasings per IR node type, read by the rule tier alone (C18).

Each phrasing is checked by language, not tree shape: the reading must describe the
same language as the hand-written IR over the same alphabet.
"""

from typing import Any

import pytest

from nfa_studio.interpret import interpret
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.session.clarify import Ready, open_draft
from tests.benchmark.run_benchmark import same_language

Spec = dict[str, Any]


def starts(p: str) -> Spec:
    return {"type": "starts_with", "pattern": p}


def ends(p: str) -> Spec:
    return {"type": "ends_with", "pattern": p}


def contains(p: str) -> Spec:
    return {"type": "contains", "pattern": p}


def avoids(p: str) -> Spec:
    return {"type": "avoids", "pattern": p}


def count(s: str, op: str, n: int) -> Spec:
    return {"type": "symbol_count", "symbol": s, "op": op, "n": n}


def parity(s: str, even: bool) -> Spec:
    return {"type": "symbol_parity", "symbol": s, "parity": "even" if even else "odd"}


def length_mod(m: int, r: int) -> Spec:
    return {"type": "length_mod", "m": m, "r": r}


def pcount(p: str, op: str, n: int, overlap: bool = False) -> Spec:
    return {"type": "pattern_count", "pattern": p, "op": op, "n": n, "overlap": overlap}


def regex(expr: str) -> Spec:
    return {"type": "regex", "expr": expr}


def words(*listed: str) -> Spec:
    return {"type": "literal_set", "words": list(listed)}


def both(*children: Spec) -> Spec:
    return {"type": "and", "children": list(children)}


def either(*children: Spec) -> Spec:
    return {"type": "or", "children": list(children)}


def negated(child: Spec) -> Spec:
    return {"type": "not", "child": child}


AB, BIN = "ab", "01"

# (node type the phrasing exercises, description, expected language, alphabet)
PHRASINGS: list[tuple[str, str, Spec, str]] = [
    # starts_with
    ("starts_with", "binary strings that start with 1", starts("1"), BIN),
    ("starts_with", "strings over {a,b} beginning with ab", starts("ab"), AB),
    ("starts_with", "words that begin with ab, over {a,b}", starts("ab"), AB),
    ("starts_with", "strings over {a,b} whose first symbol is a", starts("a"), AB),
    ("starts_with", "strings over {a,b} with prefix ab", starts("ab"), AB),
    ("starts_with", "Strings over {a,b} starting in ab", starts("ab"), AB),
    ("starts_with", "strings over {a,b} that statr with ab", starts("ab"), AB),
    ("starts_with", "binary strings that begin with a 1", starts("1"), BIN),
    ("starts_with", "the first two symbols are ab, over {a,b}", starts("ab"), AB),
    # ends_with
    ("ends_with", "binary strings ending in 01", ends("01"), BIN),
    ("ends_with", "binary strings that end with 01", ends("01"), BIN),
    ("ends_with", "binary strings which finish with 01", ends("01"), BIN),
    ("ends_with", "binary strings whose last two symbols are 01", ends("01"), BIN),
    ("ends_with", "binary strings with suffix 01", ends("01"), BIN),
    ("ends_with", "binary strings ending with a 1", ends("1"), BIN),
    ("ends_with", "binary strings that ends in 01", ends("01"), BIN),
    ("ends_with", "binary strings endign in 01", ends("01"), BIN),
    ("ends_with", "binary strings whose last bit is 1", ends("1"), BIN),
    # contains
    ("contains", "binary strings containing 101", contains("101"), BIN),
    ("contains", "binary strings that have 101 as a substring", contains("101"), BIN),
    ("contains", "binary strings with the substring 101", contains("101"), BIN),
    ("contains", "binary strings in which 101 appears", contains("101"), BIN),
    ("contains", "binary strings that include 101", contains("101"), BIN),
    ("contains", "binary strings that has 101", contains("101"), BIN),
    ("contains", "binary strings contianing 101", contains("101"), BIN),
    ("contains", "binary strings where 101 occurs somewhere", contains("101"), BIN),
    ("contains", "binary strings with at least one occurrence of 101", contains("101"), BIN),
    # avoids
    ("avoids", "binary strings that don't contain 11", avoids("11"), BIN),
    ("avoids", "binary strings without 11", avoids("11"), BIN),
    ("avoids", "binary strings that never have 11", avoids("11"), BIN),
    ("avoids", "binary strings avoiding 11", avoids("11"), BIN),
    ("avoids", "binary strings in which 11 does not appear", avoids("11"), BIN),
    ("avoids", "binary strings that do not have the substring 11", avoids("11"), BIN),
    ("avoids", "binary strings with no 11", avoids("11"), BIN),
    ("avoids", "binary strings free of 11", avoids("11"), BIN),
    ("avoids", "binary strings that doesnt contain 11", avoids("11"), BIN),
    # symbol_count
    ("symbol_count", "strings over {a,b} with exactly three a's", count("a", "eq", 3), AB),
    ("symbol_count", "strings over {a,b} with exactly 3 a's", count("a", "eq", 3), AB),
    ("symbol_count", "strings over {a,b} containing at least two b's", count("b", "ge", 2), AB),
    ("symbol_count", "strings over {a,b} with at most one a", count("a", "le", 1), AB),
    ("symbol_count", "strings over {a,b} with more than 2 a's", count("a", "ge", 3), AB),
    ("symbol_count", "binary strings with fewer than three 1s", count("1", "le", 2), BIN),
    ("symbol_count", "strings over {a,b} where a appears exactly twice", count("a", "eq", 2), AB),
    (
        "symbol_count",
        "strings over {a,b} in which the number of a's is exactly 2",
        count("a", "eq", 2),
        AB,
    ),
    ("symbol_count", "strings over {a,b} having no more than two bs", count("b", "le", 2), AB),
    # symbol_parity
    ("symbol_parity", "even number of 1s", parity("1", True), BIN),
    ("symbol_parity", "binary strings with an odd number of 0s", parity("0", False), BIN),
    ("symbol_parity", "strings over {a,b} where the number of a's is even", parity("a", True), AB),
    (
        "symbol_parity",
        "strings over {a,b} in which a occurs an even number of times",
        parity("a", True),
        AB,
    ),
    ("symbol_parity", "strings over {a,b} with an even count of b", parity("b", True), AB),
    ("symbol_parity", "strings over {a,b} with an odd amount of a's", parity("a", False), AB),
    ("symbol_parity", "strings over {a,b} whose count of a is odd", parity("a", False), AB),
    ("symbol_parity", "binary strings having an even nubmer of 1s", parity("1", True), BIN),
    # length_mod
    ("length_mod", "strings over {a,b} of even length", length_mod(2, 0), AB),
    ("length_mod", "binary strings of odd length", length_mod(2, 1), BIN),
    ("length_mod", "binary strings whose length is a multiple of 3", length_mod(3, 0), BIN),
    ("length_mod", "binary strings with length divisible by 4", length_mod(4, 0), BIN),
    ("length_mod", "binary strings whose length is 1 mod 3", length_mod(3, 1), BIN),
    ("length_mod", "binary strings with length congruent to 2 modulo 5", length_mod(5, 2), BIN),
    ("length_mod", "strings over {a,b} with an even length", length_mod(2, 0), AB),
    ("length_mod", "binary strings whose length is divisible by three", length_mod(3, 0), BIN),
    ("length_mod", "binary strings whose length is not even", length_mod(2, 1), BIN),
    # pattern_count
    (
        "pattern_count",
        "strings over {a,b} with exactly two occurrences of ab",
        pcount("ab", "eq", 2),
        AB,
    ),
    ("pattern_count", "strings over {a,b} containing ab at least twice", pcount("ab", "ge", 2), AB),
    (
        "pattern_count",
        "strings over {a,b} where ab appears exactly 2 times",
        pcount("ab", "eq", 2),
        AB,
    ),
    (
        "pattern_count",
        "strings over {a,b} with at most one occurrence of ab",
        pcount("ab", "le", 1),
        AB,
    ),
    ("pattern_count", "strings over {a,b} with ab exactly three times", pcount("ab", "eq", 3), AB),
    (
        "pattern_count",
        "binary strings with exactly two occurrences of 10",
        pcount("10", "eq", 2),
        BIN,
    ),
    ("pattern_count", "strings over {a,b,c} containing abc twice", pcount("abc", "ge", 2), "abc"),
    (
        "pattern_count",
        "strings over {a,b} with at least 2 instances of ab",
        pcount("ab", "ge", 2),
        AB,
    ),
    # regex
    ("regex", "(a|b)*abb", regex("(a|b)*abb"), AB),
    ("regex", "regex (a|b)*abb", regex("(a|b)*abb"), AB),
    ("regex", "strings matching (a|b)*abb", regex("(a|b)*abb"), AB),
    ("regex", "the regular expression a*b*", regex("a*b*"), AB),
    ("regex", "a(a|b)*b", regex("a(a|b)*b"), AB),
    ("regex", "strings described by (ab)*", regex("(ab)*"), AB),
    ("regex", "(0|1)*00", regex("(0|1)*00"), BIN),
    ("regex", "strings of the form a*b*", regex("a*b*"), AB),
    ("regex", "Σ={a,b}: (a|b)*abb", regex("(a|b)*abb"), AB),
    # literal_set
    ("literal_set", "{0, 10, 110}", words("0", "10", "110"), BIN),
    ("literal_set", "0, 10 and 110", words("0", "10", "110"), BIN),
    ("literal_set", "strings like ab, abab, ababab", words("ab", "abab", "ababab"), AB),
    ("literal_set", "strings equal to one of: 0, 10, 110", words("0", "10", "110"), BIN),
    ("literal_set", "exactly the words a, ab and abb", words("a", "ab", "abb"), AB),
    ("literal_set", "only the strings 0 and 1", words("0", "1"), BIN),
    ("literal_set", "just the words ab, ba", words("ab", "ba"), AB),
    ("literal_set", "the set {ab, ba} over {a,b}", words("ab", "ba"), AB),
    ("literal_set", "the strings 0, 10 or 110", words("0", "10", "110"), BIN),
    # and
    ("and", "binary strings that start with 1 and end with 0", both(starts("1"), ends("0")), BIN),
    ("and", "contains 101 and ends with 00", both(contains("101"), ends("00")), BIN),
    (
        "and",
        "strings over {a,b} starting with a as well as ending with b",
        both(starts("a"), ends("b")),
        AB,
    ),
    (
        "and",
        "binary strings with even length that contain 11",
        both(length_mod(2, 0), contains("11")),
        BIN,
    ),
    (
        "and",
        "binary strings which start with 1 plus have an even number of 0s",
        both(starts("1"), parity("0", True)),
        BIN,
    ),
    (
        "and",
        "strings over {a,b} that contain aa but also end with b",
        both(contains("aa"), ends("b")),
        AB,
    ),
    (
        "and",
        "binary strings that both start with 0 and end with 1",
        both(starts("0"), ends("1")),
        BIN,
    ),
    (
        "and",
        "strings over {a,b} of odd length that end in a",
        both(length_mod(2, 1), ends("a")),
        AB,
    ),
    ("and", "strings over {a,b} that begin and end with a", both(starts("a"), ends("a")), AB),
    # or
    ("or", "binary strings that start with 0 or end with 1", either(starts("0"), ends("1")), BIN),
    ("or", "strings over {a,b} containing aa or bb", either(contains("aa"), contains("bb")), AB),
    ("or", "binary strings ending in 00 or 11", either(ends("00"), ends("11")), BIN),
    (
        "or",
        "strings over {a,b} that either start with a or end with a",
        either(starts("a"), ends("a")),
        AB,
    ),
    (
        "or",
        "binary strings with even length or containing 11",
        either(length_mod(2, 0), contains("11")),
        BIN,
    ),
    (
        "or",
        "strings over {a,b} that begin with b or have an odd number of a's",
        either(starts("b"), parity("a", False)),
        AB,
    ),
    ("or", "contains 101 or ends with 00", either(contains("101"), ends("00")), BIN),
    ("or", "binary strings that start with 1, or end with 1", either(starts("1"), ends("1")), BIN),
    # not
    ("not", "binary strings that do not end with 00", negated(ends("00")), BIN),
    ("not", "binary strings not ending in 00", negated(ends("00")), BIN),
    ("not", "binary strings that don't start with 1", negated(starts("1")), BIN),
    (
        "not",
        "strings over {a,b} that do not have an even number of a's",
        negated(parity("a", True)),
        AB,
    ),
    ("not", "binary strings that are not of even length", negated(length_mod(2, 0)), BIN),
    ("not", "strings over {a,b} that never start with b", negated(starts("b")), AB),
    ("not", "binary strings that doesnt end with 1", negated(ends("1")), BIN),
    (
        "not",
        "contains 101 but does not end with 00",
        both(contains("101"), negated(ends("00"))),
        BIN,
    ),
    # concat (k-th symbols and exact lengths)
    (
        "concat",
        "binary strings whose third symbol from the end is 1",
        regex("(0|1)*1(0|1)(0|1)"),
        BIN,
    ),
    ("concat", "binary strings whose second symbol is 0", regex("(0|1)0(0|1)*"), BIN),
    ("concat", "binary strings of length exactly 3", regex("(0|1)(0|1)(0|1)"), BIN),
    ("concat", "strings over {a,b} whose second-to-last symbol is a", regex("(a|b)*a(a|b)"), AB),
    (
        "concat",
        "binary strings where the 2nd symbol from the start is 1",
        regex("(0|1)1(0|1)*"),
        BIN,
    ),
    ("concat", "binary strings of length 2", regex("(0|1)(0|1)"), BIN),
    ("concat", "binary strings where the third symbol is 1", regex("(0|1)(0|1)1(0|1)*"), BIN),
    ("concat", "binary strings whose second last symbol is 1", regex("(0|1)*1(0|1)"), BIN),
    # star (repetition)
    (
        "star",
        "strings over {a,b} in which every a is immediately followed by b",
        regex("(b|ab)*"),
        AB,
    ),
    ("star", "strings over {a,b} where each b is preceded by a", regex("(a|ab)*"), AB),
    ("star", "binary strings of length at least 2", regex("(0|1)(0|1)(0|1)*"), BIN),
    ("star", "strings over {a,b} where every a is followed by b", regex("(b|ab)*"), AB),
    ("star", "zero or more copies of ab", regex("(ab)*"), AB),
    ("star", "any number of repetitions of ab", regex("(ab)*"), AB),
    ("star", "one or more copies of ab", regex("ab(ab)*"), AB),
    ("star", "every 0 is followed by 1, over {0,1}", regex("(1|01)*"), BIN),
    ("star", "strings over {a,b} where every second symbol is a", regex("((a|b)a)*(a|b|())"), AB),
    ("star", "strings over {a,b} that look like b followed by one or more a's", regex("baa*"), AB),
    # The alphabet as "strings of …", digits as words, and other everyday wordings.
    ("starts_with", "words made of 0s and 1s that start with 0", starts("0"), BIN),
    ("symbol_count", "strings of x's and y's with at least one y", count("y", "ge", 1), "xy"),
    ("contains", "binary strings that contain three 0s in a row", contains("000"), BIN),
    ("avoids", "strings over {a,b} where a never appears right before b", avoids("ab"), AB),
    ("not", "strings over {a,b} except the ones that end with a", negated(ends("a")), AB),
    ("length_mod", "odd-length strings over {a,b}", length_mod(2, 1), AB),
    ("concat", "strings over {a,b} with b as the second symbol", regex("(a|b)b(a|b)*"), AB),
    ("symbol_count", "binary strings with 2 or fewer 1s", count("1", "le", 2), BIN),
    ("concat", "strings over {a,b} of length from 1 to 3", regex("(a|b)(a|b)?(a|b)?"), AB),
    ("symbol_parity", "binary words with an odd number of ones", parity("1", False), BIN),
    ("ends_with", "a word is accepted if it ends with 11, over {0,1}", ends("11"), BIN),
    ("contains", "strings over {a,b} that have ba anywhere", contains("ba"), AB),
    ("literal_set", "strings over {a,b} that are just ab", words("ab"), AB),
]


@pytest.mark.parametrize(
    ("node", "text", "language", "symbols"),
    PHRASINGS,
    ids=[f"{node}: {text}" for node, text, _, _ in PHRASINGS],
)
def test_paraphrase(node: str, text: str, language: Spec, symbols: str) -> None:
    result = open_draft(interpret(text), text)
    assert isinstance(result, Ready), result
    expected = validate_ir(
        {"alphabet": {"symbols": list(symbols), "source": "user"}, "language": language}
    )
    assert list(result.ir.alphabet.symbols) == list(symbols)
    assert same_language(result.ir, expected), result.ir.language.model_dump(mode="json")


def test_every_node_type_has_eight_phrasings() -> None:
    per_node: dict[str, int] = {}
    for node, *_ in PHRASINGS:
        per_node[node] = per_node.get(node, 0) + 1
    assert len(per_node) == 15
    assert min(per_node.values()) >= 8, per_node


def test_a_corrected_spelling_is_shown_on_the_confirm_screen() -> None:
    result = open_draft(interpret("binary strings endign in 01"), "binary strings endign in 01")
    assert isinstance(result, Ready)
    shown = {a.id: a.text for a in result.ir.assumptions}
    assert shown["spelling_corrected"] == "Read 'endign' as 'ending'."


@pytest.mark.parametrize(
    "text", ["strings over {a,b} containing abba", "strings over {a,b,c} containing cabab"]
)
def test_patterns_and_readable_text_are_never_respelled(text: str) -> None:
    result = open_draft(interpret(text), text)
    assert isinstance(result, Ready)
    assert "spelling_corrected" not in {a.id for a in result.ir.assumptions}
