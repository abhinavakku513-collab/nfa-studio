import hashlib
import json
import re

import pytest

from nfa_studio.core.model import (
    EPS,
    Automaton,
    canonical_json,
    dead_states,
    model_hash,
    reachable,
    trim,
)
from tests.support.machines import ENDS_WITH_AB, machine


def test_hash_has_the_canonical_form() -> None:
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", model_hash(ENDS_WITH_AB))


def test_hash_ignores_metadata_and_insertion_order() -> None:
    edges = [("q0", "a", "q0"), ("q0", "b", "q0"), ("q0", "a", "q1"), ("q1", "b", "q2")]
    reordered = machine(
        list(reversed(edges)),
        final={"q2"},
        kind="enfa",
        meanings={"q0": "something else"},
    )
    assert model_hash(reordered) == model_hash(ENDS_WITH_AB)


def test_hash_changes_with_the_language_defining_parts() -> None:
    other_final = machine(
        [("q0", "a", "q0"), ("q0", "b", "q0"), ("q0", "a", "q1"), ("q1", "b", "q2")],
        final={"q1", "q2"},
    )
    assert model_hash(other_final) != model_hash(ENDS_WITH_AB)


def test_canonical_json_writes_epsilon_and_sorts_everything() -> None:
    auto = machine([("q0", "ε", "q1"), ("q0", "b", "q1"), ("q0", "a", "q1")], final={"q1"})
    payload = {
        "Q": ["q0", "q1"],
        "Sigma": ["a", "b"],
        "delta": [["q0", "a", ["q1"]], ["q0", "b", ["q1"]], ["q0", "ε", ["q1"]]],
        "q0": "q0",
        "F": ["q1"],
    }
    assert canonical_json(payload) == json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

    expected = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    assert model_hash(auto) == "sha256:" + expected


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"start": "zz"}, "start state 'zz' is not in Q"),
        ({"final": frozenset({"zz"})}, "F names unknown state 'zz'"),
        ({"alphabet": ("b", "a")}, "Σ is not sorted and unique"),
        ({"alphabet": ("ab",)}, "not one character"),
        ({"delta": {("q0", "c"): frozenset({"q0"})}}, "not in Σ ∪ {ε}"),
        ({"delta": {("q0", "a"): frozenset({"zz"})}}, "edge to unknown state 'zz'"),
        ({"delta": {("q0", EPS): frozenset({"q0"})}, "kind": "nfa"}, "has an ε edge"),
        (
            {"delta": {("q0", "a"): frozenset({"q0", "q1"})}, "kind": "dfa"},
            "a DFA has 2 targets",
        ),
    ],
)
def test_malformed_machines_are_rejected(kwargs: dict[str, object], message: str) -> None:
    fields: dict[str, object] = {
        "states": ("q0", "q1"),
        "alphabet": ("a", "b"),
        "delta": {},
        "start": "q0",
        "final": frozenset({"q1"}),
    }
    with pytest.raises(ValueError, match=re.escape(message)):
        Automaton(**{**fields, **kwargs})


def test_delta_cannot_be_mutated_after_construction() -> None:
    delta = {("q0", "a"): frozenset({"q0"})}
    auto = Automaton(("q0",), ("a",), delta, "q0", frozenset({"q0"}))
    delta[("q0", "a")] = frozenset()
    assert auto.targets("q0", "a") == {"q0"}
    with pytest.raises(TypeError):
        auto.delta[("q0", "a")] = frozenset()


def test_trim_removes_unreachable_states_and_marks_dead_ones() -> None:
    auto = machine(
        [("q0", "a", "q1"), ("q0", "b", "q2"), ("q2", "a", "q2"), ("q3", "a", "q1")],
        final={"q1"},
    )
    assert reachable(auto) == {"q0", "q1", "q2"}
    trimmed = trim(auto)
    assert trimmed.states == ("q0", "q1", "q2")
    assert trimmed.dead == {"q2"}


def test_every_state_is_dead_when_no_accepting_state_is_reachable() -> None:
    auto = machine([("q0", "a", "q1")], final=(), extra_states=["q2"])
    assert dead_states(auto) == {"q0", "q1", "q2"}
    assert trim(auto).states == ("q0", "q1")
