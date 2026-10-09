from itertools import count, product
from typing import Any

import pytest

from nfa_studio.compile import EMPTY_LANGUAGE_WARNING, Compiled, compile
from nfa_studio.compile.atoms import Builder
from nfa_studio.compile.naming import name_states
from nfa_studio.core.model import EPS, model_hash
from nfa_studio.core.simulate import accepts
from nfa_studio.ir.limits import Budget, StateLimitExceeded, TimeBudgetExceeded
from nfa_studio.ir.normalize import IRInvalid, validate_ir
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import NODE_TYPES
from tests.support.machines import accepted_words


def build(language: dict[str, Any], symbols: str = "ab", budget: Budget | None = None) -> Compiled:
    doc = validate_ir(
        {"alphabet": {"symbols": list(symbols), "source": "user"}, "language": language}
    )
    return compile(doc, budget)


def delta_table(compiled: Compiled) -> dict[tuple[str, str], set[str]]:
    return {key: set(dsts) for key, dsts in compiled.automaton.delta.items()}


def test_spec_7_5_ends_with_ab() -> None:
    auto = build({"type": "ends_with", "pattern": "ab"}).automaton
    assert auto.states == ("q0", "q1", "q2")
    assert auto.start == "q0"
    assert {k: set(v) for k, v in auto.delta.items()} == {
        ("q0", "a"): {"q0", "q1"},
        ("q0", "b"): {"q0"},
        ("q1", "b"): {"q2"},
    }
    assert auto.final == {"q2"}


def test_spec_7_6_not_containing_aa() -> None:
    compiled = build({"type": "avoids", "pattern": "aa"})
    auto = compiled.automaton
    assert auto.states == ("q0", "q1", "q2")
    assert delta_table(compiled) == {
        ("q0", "a"): {"q1"},
        ("q0", "b"): {"q0"},
        ("q1", "a"): {"q2"},
        ("q1", "b"): {"q0"},
        ("q2", "a"): {"q2"},
        ("q2", "b"): {"q2"},
    }
    assert auto.final == {"q0", "q1"}
    assert auto.dead == {"q2"}


def test_not_contains_is_the_same_language_built_by_complement() -> None:
    # §7.6 calls the result 3 states; complementing §7.1's contains NFA really gives 4,
    # because the subsets {q0,q1,q2} and {q0,q2} are distinct before minimisation.
    via_not = build({"type": "not", "child": {"type": "contains", "pattern": "aa"}}).automaton
    direct = build({"type": "avoids", "pattern": "aa"}).automaton
    assert accepted_words(via_not, 8) == accepted_words(direct, 8)
    assert via_not.kind == "dfa"
    assert len(via_not.states) == 4


EVERY_NODE: list[tuple[dict[str, Any], list[str], list[str]]] = [
    ({"type": "starts_with", "pattern": "ab"}, ["ab", "abba"], ["", "a", "ba"]),
    ({"type": "ends_with", "pattern": "ab"}, ["ab", "bbab"], ["", "aba", "abb"]),
    ({"type": "contains", "pattern": "aa"}, ["aa", "baab"], ["", "aba"]),
    ({"type": "avoids", "pattern": "aa"}, ["", "aba", "b"], ["aa", "baab"]),
    ({"type": "symbol_count", "symbol": "b", "op": "eq", "n": 2}, ["bb", "abab"], ["b", "bbb"]),
    ({"type": "symbol_count", "symbol": "b", "op": "ge", "n": 2}, ["bb", "bbb"], ["", "ab"]),
    ({"type": "symbol_count", "symbol": "b", "op": "le", "n": 1}, ["", "ab"], ["bb"]),
    ({"type": "symbol_parity", "symbol": "a", "parity": "even"}, ["", "aa", "baba"], ["a"]),
    ({"type": "symbol_parity", "symbol": "a", "parity": "odd"}, ["a", "abaa"], ["", "aa"]),
    ({"type": "length_mod", "m": 3, "r": 0}, ["", "abb"], ["a", "ab"]),
    (
        {"type": "pattern_count", "pattern": "aba", "op": "ge", "n": 2, "overlap": True},
        ["ababa"],
        ["aba", "abba"],
    ),
    (
        {"type": "pattern_count", "pattern": "aba", "op": "ge", "n": 2, "overlap": False},
        ["abaaba"],
        ["ababa"],
    ),
    ({"type": "regex", "expr": "(b|ab)*"}, ["", "b", "ab", "bab"], ["a", "aab", "ba"]),
    ({"type": "regex", "expr": "a*b*"}, ["", "aab", "b"], ["ba"]),
    ({"type": "literal_set", "words": ["", "ab", "b"]}, ["", "ab", "b"], ["a", "abb", "ba"]),
    (
        {
            "type": "and",
            "children": [
                {"type": "starts_with", "pattern": "a"},
                {"type": "ends_with", "pattern": "b"},
            ],
        },
        ["ab", "aab"],
        ["", "a", "ba"],
    ),
    (
        {
            "type": "or",
            "children": [
                {"type": "contains", "pattern": "aa"},
                {"type": "ends_with", "pattern": "bb"},
            ],
        },
        ["aa", "abb"],
        ["ab", ""],
    ),
    ({"type": "not", "child": {"type": "ends_with", "pattern": "b"}}, ["", "a", "ba"], ["b", "ab"]),
    (
        {
            "type": "concat",
            "children": [
                {"type": "literal_set", "words": ["a"]},
                {"type": "star", "child": {"type": "literal_set", "words": ["b"]}},
            ],
        },
        ["a", "abbb"],
        ["", "b", "aba"],
    ),
    (
        {"type": "star", "child": {"type": "literal_set", "words": ["ab", "b"]}},
        ["", "b", "abab", "bab"],
        ["a", "aba"],
    ),
]


@pytest.mark.parametrize(
    ("language", "yes", "no"),
    EVERY_NODE,
    ids=[f"{e[0]['type']}-{i}" for i, e in enumerate(EVERY_NODE)],
)
def test_every_node_type_on_hand_computed_words(
    language: dict[str, Any], yes: list[str], no: list[str]
) -> None:
    compiled = build(language)
    auto = compiled.automaton
    assert all(accepts(auto, w) for w in yes)
    assert not any(accepts(auto, w) for w in no)
    # Hand-picked words can miss a case; the independent oracle (C6) sees every word.
    ir = validate_ir({"alphabet": {"symbols": ["a", "b"], "source": "user"}, "language": language})
    for n in range(7):
        for letters in product("ab", repeat=n):
            word = "".join(letters)
            assert accepts(auto, word) == matches(ir.language, word), word


def test_every_node_type_is_covered() -> None:
    assert {language["type"] for language, _, _ in EVERY_NODE} == set(NODE_TYPES)


AND_OR = {
    "type": "or",
    "children": [
        {
            "type": "and",
            "children": [
                {"type": "starts_with", "pattern": "a"},
                {"type": "symbol_parity", "symbol": "b", "parity": "odd"},
                {"type": "not", "child": {"type": "contains", "pattern": "bb"}},
            ],
        },
        {"type": "regex", "expr": "(ab)*"},
        {"type": "length_mod", "m": 2, "r": 1},
    ],
}


def test_same_ir_twice_gives_the_same_hash() -> None:
    first, second = build(AND_OR).automaton, build(AND_OR).automaton
    assert model_hash(first) == model_hash(second)
    assert first.states == second.states
    assert dict(first.meanings) == dict(second.meanings)


def test_permuted_and_or_children_give_the_same_hash() -> None:
    permuted = {
        "type": "or",
        "children": [
            {"type": "length_mod", "m": 2, "r": 1},
            {"type": "regex", "expr": "(ab)*"},
            {
                "type": "and",
                "children": [
                    {"type": "not", "child": {"type": "contains", "pattern": "bb"}},
                    {"type": "starts_with", "pattern": "a"},
                    {"type": "symbol_parity", "symbol": "b", "parity": "odd"},
                ],
            },
        ],
    }
    assert model_hash(build(permuted, "ba").automaton) == model_hash(build(AND_OR).automaton)


def test_naming_visits_symbols_in_alphabet_order_then_epsilon() -> None:
    b = Builder(("a", "b"))
    s0, s1, s2, s3, s4 = (b.state(f"made {i}") for i in range(5))
    b.edge(s0, EPS, s1)
    b.edge(s0, "b", s2)
    b.edge(s0, "a", s4)
    b.edge(s0, "a", s3)
    named = name_states(b.build(s0, [s1]))
    # a first (s3 before s4 by creation order), then b, then ε.
    assert [named.meanings[q] for q in named.states] == [
        "made 0",
        "made 3",
        "made 4",
        "made 2",
        "made 1",
    ]


def test_atom_bigger_than_the_cap_is_refused() -> None:
    # 16 KMP positions × 21 counter values, plus the dead state: 337 states.
    with pytest.raises(StateLimitExceeded) as caught:
        build({"type": "pattern_count", "pattern": "ab" * 8, "op": "eq", "n": 20, "overlap": False})
    assert caught.value.code == "E_STATE_LIMIT"
    assert caught.value.size > 200


def test_product_bigger_than_the_cap_is_refused() -> None:
    # 14 and 15 are coprime, so all 210 pairs are reachable.
    with pytest.raises(StateLimitExceeded) as caught:
        build(
            {
                "type": "and",
                "children": [
                    {"type": "length_mod", "m": 14, "r": 0},
                    {"type": "length_mod", "m": 15, "r": 0},
                ],
            }
        )
    assert caught.value.size == 201


def test_subset_construction_bigger_than_the_cap_is_refused() -> None:
    # The 8th symbol from the end is a: 2^8 subsets.
    with pytest.raises(StateLimitExceeded):
        build(
            {
                "type": "not",
                "child": {"type": "regex", "expr": "(a|b)*a(a|b)(a|b)(a|b)(a|b)(a|b)(a|b)(a|b)"},
            }
        )


def test_time_budget_applies_to_the_whole_compilation() -> None:
    ticks = count()
    budget = Budget(seconds=3, clock=lambda: float(next(ticks)))
    with pytest.raises(TimeBudgetExceeded) as caught:
        build(AND_OR, budget=budget)
    assert caught.value.code == "E_TIMEOUT"


def test_empty_language_is_returned_with_a_warning() -> None:
    compiled = build(
        {
            "type": "and",
            "children": [
                {"type": "starts_with", "pattern": "a"},
                {"type": "starts_with", "pattern": "b"},
            ],
        }
    )
    assert compiled.automaton.final == frozenset()
    assert compiled.warnings == (EMPTY_LANGUAGE_WARNING,)
    assert build({"type": "contains", "pattern": "a"}).warnings == ()


def test_log_records_each_node_in_post_order() -> None:
    compiled = build(
        {
            "type": "and",
            "children": [
                {"type": "symbol_parity", "symbol": "a", "parity": "even"},
                {"type": "not", "child": {"type": "contains", "pattern": "bb"}},
            ],
        }
    )
    assert [e.node for e in compiled.log] == ["contains", "not", "symbol_parity", "and", "naming"]
    not_entry = compiled.log[1]
    assert "DFA produced by complement" in not_entry.text
    assert not_entry.states == 4
    assert compiled.log[-1].states == len(compiled.automaton.states)


def test_log_mentions_dead_states() -> None:
    naming = build({"type": "avoids", "pattern": "aa"}).log[-1]
    assert "1 state cannot reach an accepting state" in naming.text


def test_regex_syntax_errors_become_schema_errors() -> None:
    with pytest.raises(IRInvalid, match=r"position 3: empty alternative") as caught:
        build({"type": "regex", "expr": "a|"})
    assert caught.value.code == "E_SCHEMA_INVALID"
