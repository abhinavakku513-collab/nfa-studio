"""Phase 3 exit criterion (spec §15): an injected bug is caught with a counterexample."""

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from nfa_studio.compile import compile
from nfa_studio.core.model import EPS, Automaton
from nfa_studio.core.simulate import accepts
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import IRDocument
from nfa_studio.reference.equivalence import language_difference
from nfa_studio.verify.ladder import VerificationFailed, verify

BENCHMARK = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_v1.json"


def benchmark_specs() -> list[tuple[int, IRDocument]]:
    entries = json.loads(BENCHMARK.read_text(encoding="utf-8"))["entries"]
    return [
        (
            e["id"],
            validate_ir(
                {
                    "alphabet": {"symbols": e["expect"]["alphabet"], "source": "user"},
                    "language": e["expect"]["language"],
                }
            ),
        )
        for e in entries
        if e["expect"]["kind"] == "ir"
    ]


def edges(auto: Automaton) -> list[tuple[str, str, str]]:
    return sorted((q, a, r) for (q, a), dsts in auto.delta.items() for r in dsts)


def with_edges(auto: Automaton, new: list[tuple[str, str, str]]) -> Automaton:
    delta: dict[tuple[str, str], set[str]] = {}
    for q, a, r in new:
        delta.setdefault((q, a), set()).add(r)
    kind = "enfa" if any(a == EPS for _, a, _ in new) else auto.kind
    if kind == "dfa" and any(len(dsts) > 1 for dsts in delta.values()):
        kind = "nfa"
    return replace(
        auto, delta={k: frozenset(v) for k, v in delta.items()}, kind=kind, dead=frozenset()
    )


def flip_accepting(auto: Automaton) -> Iterator[Automaton]:
    for q in auto.states:
        yield replace(auto, final=auto.final ^ {q})


def redirect_edge(auto: Automaton) -> Iterator[Automaton]:
    original = edges(auto)
    for i, (q, a, r) in enumerate(original):
        for other in auto.states:
            if other != r and (q, a, other) not in original:
                yield with_edges(auto, [*original[:i], (q, a, other), *original[i + 1 :]])


def delete_edge(auto: Automaton) -> Iterator[Automaton]:
    original = edges(auto)
    for i in range(len(original)):
        yield with_edges(auto, original[:i] + original[i + 1 :])


def add_epsilon_edge(auto: Automaton) -> Iterator[Automaton]:
    original = edges(auto)
    for q in auto.states:
        for r in auto.states:
            if q != r and (q, EPS, r) not in original:
                yield with_edges(auto, [*original, (q, EPS, r)])


MUTATIONS: dict[str, Callable[[Automaton], Iterator[Automaton]]] = {
    "flip an accepting state": flip_accepting,
    "redirect an edge": redirect_edge,
    "delete an edge": delete_edge,
    "add a stray ε edge": add_epsilon_edge,
}

SPECS = benchmark_specs()


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize(("entry", "spec"), SPECS, ids=[f"#{e}" for e, _ in SPECS])
def test_ladder_catches_the_mutant(entry: int, spec: IRDocument, mutation: str) -> None:
    original = compile(spec).automaton
    verify(original, spec)
    # The first mutant that really changes the language; equal-language mutants are
    # not bugs. The verified original is the ground truth for "changes".
    mutant = next(
        (m for m in MUTATIONS[mutation](original) if language_difference(m, original) is not None),
        None,
    )
    assert mutant is not None, f"no {mutation} mutant of #{entry} changes the language"
    with pytest.raises(VerificationFailed) as caught:
        verify(mutant, spec)
    word = caught.value.counterexample
    assert word is not None
    assert accepts(mutant, word) != matches(spec.language, word), (entry, mutation, word)


def test_mutations_cover_at_least_ten_specifications() -> None:
    assert len(SPECS) >= 10
