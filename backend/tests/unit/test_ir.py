import json
import typing
from pathlib import Path
from typing import Any

import pytest

from nfa_studio.ir.limits import LIMITS
from nfa_studio.ir.normalize import IRInvalid, normalize, spec_hash, validate_ir
from nfa_studio.ir.schema import (
    NODE_TYPES,
    And,
    Contains,
    EndsWith,
    LiteralSet,
    Node,
    Not,
    Or,
    StartsWith,
    SymbolParity,
)

BENCHMARK = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_v1.json"


def doc(language: dict[str, Any], symbols: list[str] | None = None) -> dict[str, Any]:
    return {
        "ir_version": "1.0",
        "alphabet": {"symbols": ["a", "b"] if symbols is None else symbols, "source": "user"},
        "language": language,
    }


def invalid(data: dict[str, Any]) -> str:
    with pytest.raises(IRInvalid) as caught:
        validate_ir(data)
    assert caught.value.code == "E_SCHEMA_INVALID"
    return str(caught.value)


def benchmark_irs() -> list[tuple[int, dict[str, Any]]]:
    entries = json.loads(BENCHMARK.read_text(encoding="utf-8"))["entries"]
    return [
        (e["id"], doc(e["expect"]["language"], e["expect"]["alphabet"]))
        for e in entries
        if e["expect"]["kind"] == "ir"
    ]


@pytest.mark.parametrize(("entry", "data"), benchmark_irs())
def test_every_benchmark_ir_validates(entry: int, data: dict[str, Any]) -> None:
    validate_ir(data)


def test_node_types_match_the_schema_union() -> None:
    union = typing.get_args(typing.get_args(Node)[0])
    assert tuple(model.model_fields["type"].default for model in union) == NODE_TYPES


@pytest.mark.parametrize(
    ("language", "message"),
    [
        ({"type": "palindrome"}, "language"),
        ({"type": "pattern_count", "pattern": "ab", "op": "ge", "n": 2}, "overlap"),
        ({"type": "contains", "pattern": "ab", "extra": 1}, "extra"),
        ({"type": "contains", "pattern": "a" * 17}, "at most 16 characters"),
        ({"type": "contains", "pattern": ""}, "at least 1 character"),
        ({"type": "symbol_count", "symbol": "a", "op": "ge", "n": 21}, "less than or equal to 20"),
        ({"type": "regex", "expr": "a" * 201}, "at most 200 characters"),
        ({"type": "length_mod", "m": 3, "r": 3}, "r must be less than m"),
        ({"type": "and", "children": []}, "at least 1 item"),
    ],
)
def test_schema_violations(language: dict[str, Any], message: str) -> None:
    assert message in invalid(doc(language))


def test_alphabet_is_sorted_and_deduplicated() -> None:
    ir = validate_ir(doc({"type": "contains", "pattern": "ba"}, ["b", "a", "b"]))
    assert ir.alphabet.symbols == ("a", "b")


@pytest.mark.parametrize("symbol", ["(", ")", "|", "*", "+", "?", "\\", "ε"])
def test_reserved_alphabet_symbols_are_rejected(symbol: str) -> None:
    assert "reserved" in invalid(doc({"type": "length_mod", "m": 2, "r": 0}, ["a", symbol]))


@pytest.mark.parametrize(
    ("symbols", "message"),
    [
        (["a", " "], "printable non-whitespace"),
        (["a", "\n"], "printable non-whitespace"),
        (["ab"], "exactly one character"),
        ([], "the alphabet has 0 symbols"),
        (list("abcdefg"), "the alphabet has 7 symbols"),
    ],
)
def test_alphabet_rules(symbols: list[str], message: str) -> None:
    assert message in invalid(doc({"type": "length_mod", "m": 2, "r": 0}, symbols))


def test_symbols_are_case_sensitive() -> None:
    assert "symbol 'A'" in invalid(doc({"type": "contains", "pattern": "A"}))


@pytest.mark.parametrize(
    "language",
    [
        {"type": "contains", "pattern": "abc"},
        {"type": "symbol_parity", "symbol": "c", "parity": "even"},
        {"type": "regex", "expr": "(a|c)*"},
        {"type": "literal_set", "words": ["a", "bc"]},
        {
            "type": "not",
            "child": {
                "type": "pattern_count",
                "pattern": "cc",
                "op": "eq",
                "n": 1,
                "overlap": True,
            },
        },
    ],
)
def test_every_used_symbol_must_be_in_the_alphabet(language: dict[str, Any]) -> None:
    assert "symbol 'c'" in invalid(doc(language))


def test_regex_syntax_and_epsilon_are_not_symbols() -> None:
    validate_ir(doc({"type": "regex", "expr": "(a|ε)*b+()?"}))


def test_node_limit() -> None:
    leaf = {"type": "contains", "pattern": "a"}
    validate_ir(doc({"type": "or", "children": [leaf] * 39}))
    assert "41 nodes" in invalid(doc({"type": "or", "children": [leaf] * 40}))


def test_normalisation_flattens_sorts_and_removes_double_negation() -> None:
    raw = doc(
        {
            "type": "and",
            "children": [
                {
                    "type": "not",
                    "child": {"type": "not", "child": {"type": "ends_with", "pattern": "b"}},
                },
                {
                    "type": "and",
                    "children": [
                        {"type": "starts_with", "pattern": "a"},
                        {"type": "or", "children": [{"type": "contains", "pattern": "aa"}]},
                    ],
                },
            ],
        }
    )
    assert validate_ir(raw).language == And(
        children=(Contains(pattern="aa"), EndsWith(pattern="b"), StartsWith(pattern="a"))
    )


def test_odd_negation_keeps_one_not() -> None:
    triple = {
        "type": "not",
        "child": {
            "type": "not",
            "child": {"type": "not", "child": {"type": "contains", "pattern": "a"}},
        },
    }
    assert validate_ir(doc(triple)).language == Not(child=Contains(pattern="a"))


def test_literal_set_words_are_sorted_and_deduplicated() -> None:
    ir = validate_ir(doc({"type": "literal_set", "words": ["ba", "", "a", "ba"]}))
    assert ir.language == LiteralSet(words=("", "a", "ba"))


def test_or_children_are_sorted_too() -> None:
    ir = validate_ir(
        doc(
            {
                "type": "or",
                "children": [
                    {"type": "symbol_parity", "symbol": "a", "parity": "odd"},
                    {"type": "contains", "pattern": "b"},
                ],
            }
        )
    )
    assert ir.language == Or(
        children=(Contains(pattern="b"), SymbolParity(symbol="a", parity="odd"))
    )


def test_normalisation_is_idempotent_and_resets_limits() -> None:
    raw = doc({"type": "contains", "pattern": "ab"})
    raw["limits"] = {"max_states": 100_000}
    once = validate_ir(raw)
    assert once.limits == LIMITS
    assert normalize(once) == once


def test_spec_hash_ignores_child_order_alphabet_order_and_assumptions() -> None:
    left = doc(
        {
            "type": "and",
            "children": [
                {"type": "starts_with", "pattern": "a"},
                {"type": "ends_with", "pattern": "b"},
            ],
        },
        ["a", "b"],
    )
    right = doc(
        {
            "type": "and",
            "children": [
                {"type": "ends_with", "pattern": "b"},
                {"type": "starts_with", "pattern": "a"},
            ],
        },
        ["b", "a"],
    )
    right["assumptions"] = [{"id": "alphabet_inferred", "text": "…", "editable": True}]
    assert spec_hash(validate_ir(left)) == spec_hash(validate_ir(right))


def test_spec_hash_depends_on_the_language_and_the_alphabet() -> None:
    base = spec_hash(validate_ir(doc({"type": "contains", "pattern": "ab"})))
    assert base.startswith("sha256:")
    assert spec_hash(validate_ir(doc({"type": "contains", "pattern": "ba"}))) != base
    assert spec_hash(validate_ir(doc({"type": "contains", "pattern": "ab"}, ["a", "b", "c"]))) != (
        base
    )
