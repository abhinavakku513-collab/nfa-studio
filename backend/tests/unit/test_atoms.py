import pytest

from nfa_studio.compile import atoms
from nfa_studio.compile.atoms import Builder, kmp_table
from nfa_studio.compile.regex_parser import parse_regex
from nfa_studio.compile.thompson import thompson
from nfa_studio.core.model import DEAD_MEANING, EPS, Automaton
from tests.support.machines import accepted_words

AB = ("a", "b")


def accepts_exactly(auto: Automaton, yes: list[str], no: list[str]) -> None:
    accepted = accepted_words(auto, max(map(len, yes + no)))
    assert set(yes) <= accepted
    assert not set(no) & accepted


@pytest.mark.parametrize(
    ("pattern", "resume", "row_k"),
    [
        # π(m) is where an overlapping search resumes (C3).
        ("aba", 1, {3: {"a": 1, "b": 2}}),
        ("abab", 2, {4: {"a": 3, "b": 0}, 1: {"a": 1, "b": 2}}),
        ("aa", 1, {1: {"a": 2, "b": 0}, 2: {"a": 2, "b": 0}}),
        ("ab", 0, {2: {"a": 1, "b": 0}}),
    ],
)
def test_kmp_table(pattern: str, resume: int, row_k: dict[int, dict[str, int]]) -> None:
    table, border = kmp_table(pattern, AB)
    assert border == resume
    for k, row in row_k.items():
        assert table[k] == row


def test_starts_with() -> None:
    auto = atoms.starts_with("ab", AB)
    assert len(auto.states) == 3
    assert auto.kind == "dfa"
    accepts_exactly(auto, ["ab", "aba", "abbb"], ["", "a", "b", "ba", "aab"])


def test_ends_with() -> None:
    auto = atoms.ends_with("ab", AB)
    assert len(auto.states) == 3
    assert auto.kind == "nfa"
    # q_m has no outgoing edge, so passing through it early does not accept.
    assert not any(auto.targets(auto.states[-1], a) for a in AB)
    accepts_exactly(auto, ["ab", "aab", "bbab"], ["", "a", "aba", "abb"])
    assert auto.meanings[auto.states[0]] == "scanning (no commitment)"


def test_contains() -> None:
    auto = atoms.contains("aa", AB)
    assert len(auto.states) == 3
    accepts_exactly(auto, ["aa", "baab", "aab"], ["", "a", "aba", "bab"])


def test_avoids_has_an_explicit_dead_state() -> None:
    auto = atoms.avoids("aba", AB)
    assert len(auto.states) == 4
    assert auto.kind == "dfa"
    assert [auto.meanings[q] for q in auto.dead] == [DEAD_MEANING]
    accepts_exactly(auto, ["", "ab", "abba", "bbaab"], ["aba", "ababb", "baba"])


@pytest.mark.parametrize(
    ("even", "yes", "no"),
    [(True, ["", "aa", "baba"], ["a", "ab"]), (False, ["a", "abaa"], ["", "aa"])],
)
def test_symbol_parity(even: bool, yes: list[str], no: list[str]) -> None:
    auto = atoms.symbol_parity("a", even, AB)
    assert len(auto.states) == 2
    accepts_exactly(auto, yes, no)


@pytest.mark.parametrize(
    ("op", "n", "yes", "no"),
    [
        ("eq", 2, ["bb", "abab", "babaa"], ["", "b", "bbb"]),
        ("ge", 2, ["bb", "bbb", "babab"], ["", "ab", "aab"]),
        ("le", 1, ["", "ab", "aaa"], ["bb", "bab"]),
        ("ge", 0, ["", "b", "ab"], []),
        ("eq", 0, ["", "aa"], ["b", "ab"]),
    ],
)
def test_symbol_count(op: str, n: int, yes: list[str], no: list[str]) -> None:
    auto = atoms.symbol_count("b", op, n, AB)
    assert len(auto.states) == n + 1
    accepts_exactly(auto, yes, no)


def test_length_mod() -> None:
    auto = atoms.length_mod(3, 1, AB)
    assert len(auto.states) == 3
    accepts_exactly(auto, ["a", "abba"], ["", "ab", "abb"])


def test_literal_set_is_a_trie() -> None:
    auto = atoms.literal_set(("", "ab", "abb", "b"), AB)
    # Prefixes: ε, a, ab, abb, b.
    assert len(auto.states) == 5
    assert auto.start in auto.final
    accepts_exactly(auto, ["", "ab", "abb", "b"], ["a", "ba", "abbb", "bb"])


@pytest.mark.parametrize(
    ("pattern", "op", "n", "overlap", "yes", "no"),
    [
        ("aba", "ge", 2, True, ["ababa", "abaaba"], ["aba", "abba"]),
        ("aba", "ge", 2, False, ["abaaba", "abababa"], ["ababa", "aba"]),
        ("aa", "eq", 1, False, ["aa", "aaa", "baab"], ["aaaa", "a", "aabaa"]),
        ("aa", "eq", 1, True, ["aa", "baab"], ["aaa", "aaaa"]),
        ("ab", "le", 1, False, ["", "ab", "aab", "bba"], ["abab", "aabab"]),
        ("ab", "ge", 0, False, ["", "ab", "abab"], []),
    ],
)
def test_pattern_count(
    pattern: str, op: str, n: int, overlap: bool, yes: list[str], no: list[str]
) -> None:
    auto = atoms.pattern_count(pattern, op, n, overlap, AB)
    assert auto.kind == "dfa"
    accepts_exactly(auto, yes, no)


def test_pattern_count_collapses_the_saturated_count() -> None:
    # (k, c) for k < 2 and c ≤ 1, plus one "more than 1" dead state.
    auto = atoms.pattern_count("ab", "eq", 1, False, AB)
    assert len(auto.states) == 5
    assert len(auto.dead) == 1


def test_thompson_meanings_name_the_subexpression() -> None:
    auto = thompson(parse_regex("(ab)*"), AB)
    assert auto.kind == "enfa"
    assert auto.meanings[auto.start] == "inside (ab)*: start"
    assert "inside b: end" in auto.meanings.values()
    accepts_exactly(auto, ["", "ab", "abab"], ["a", "aba", "ba"])


def test_thompson_star_of_a_nullable_body_has_an_epsilon_cycle() -> None:
    auto = thompson(parse_regex("(a*)*"), AB)
    accepts_exactly(auto, ["", "a", "aaa"], ["b", "ab"])


def test_builder_reads_the_kind_off_the_structure() -> None:
    b = Builder(AB)
    q, r = b.state("q"), b.state("r")
    b.edge(q, "a", r)
    assert b.build(q, [r]).kind == "dfa"
    b.edge(q, "a", q)
    assert b.build(q, [r]).kind == "nfa"
    b.edge(r, EPS, q)
    assert b.build(q, [r]).kind == "enfa"
