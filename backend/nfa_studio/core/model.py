"""The canonical automaton model, its content hash and trimming (spec §4, §10.3)."""

import hashlib
import json
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from functools import cached_property
from types import MappingProxyType
from typing import Final, Literal

EPS: Final = ""
EPS_LABEL: Final = "ε"
DEAD_MEANING: Final = "no continuation can be accepted"

Kind = Literal["enfa", "nfa", "dfa"]
Edge = tuple[str, str, str]


@dataclass(frozen=True, eq=False)
class Automaton:
    """An immutable ε-NFA N = (Q, Σ, δ, q₀, F) with display metadata.

    `meanings`, `dead` and `kind` describe the machine for display and never enter
    `model_hash`. Equality is identity; compare machines with `model_hash`.
    Construction fails with ValueError if the machine is not well-formed (spec §8.2 V0).
    """

    states: tuple[str, ...]
    alphabet: tuple[str, ...]
    delta: Mapping[tuple[str, str], frozenset[str]]
    start: str
    final: frozenset[str]
    meanings: Mapping[str, str] = field(default_factory=dict)
    dead: frozenset[str] = frozenset()
    kind: Kind = "enfa"

    def __post_init__(self) -> None:
        # Read-only copies, so a caller's dict cannot change δ after construction.
        delta = {key: frozenset(dsts) for key, dsts in self.delta.items() if dsts}
        object.__setattr__(self, "states", tuple(self.states))
        object.__setattr__(self, "alphabet", tuple(self.alphabet))
        object.__setattr__(self, "delta", MappingProxyType(delta))
        object.__setattr__(self, "final", frozenset(self.final))
        object.__setattr__(self, "meanings", MappingProxyType(dict(self.meanings)))
        object.__setattr__(self, "dead", frozenset(self.dead))
        errors = structural_errors(self)
        if errors:
            raise ValueError("Malformed automaton: " + "; ".join(errors))

    @cached_property
    def index(self) -> Mapping[str, int]:
        """Position of each state in naming order."""
        return MappingProxyType({q: i for i, q in enumerate(self.states)})

    def targets(self, q: str, a: str) -> frozenset[str]:
        """δ(q, a), empty when there is no edge."""
        return self.delta.get((q, a), frozenset())

    def ordered(self, states: Iterable[str]) -> tuple[str, ...]:
        """`states` sorted in naming order."""
        return tuple(sorted(states, key=self.index.__getitem__))

    def meaning(self, q: str) -> str:
        return self.meanings.get(q, q)


def structural_errors(auto: Automaton) -> list[str]:
    """Every way in which `auto` violates the V0 structural rules (spec §8.2)."""
    errors: list[str] = []
    states = set(auto.states)
    if not auto.states:
        errors.append("Q is empty")
    if len(states) != len(auto.states):
        errors.append("state names are not unique")
    if not auto.alphabet:
        errors.append("Σ is empty")
    if list(auto.alphabet) != sorted(set(auto.alphabet)):
        errors.append("Σ is not sorted and unique")
    errors.extend(f"symbol {a!r} is not one character" for a in auto.alphabet if len(a) != 1)
    if auto.start not in states:
        errors.append(f"start state {auto.start!r} is not in Q")
    for name, subset in (("F", auto.final), ("dead", auto.dead), ("meanings", auto.meanings)):
        errors.extend(f"{name} names unknown state {q!r}" for q in sorted(set(subset) - states))
    labels = set(auto.alphabet) | {EPS}
    for (q, a), dsts in auto.delta.items():
        if q not in states:
            errors.append(f"δ has an edge from unknown state {q!r}")
        if a not in labels:
            errors.append(f"δ has an edge labelled {a!r}, which is not in Σ ∪ {{ε}}")
        errors.extend(f"δ has an edge to unknown state {r!r}" for r in sorted(dsts - states))
        if a == EPS and auto.kind != "enfa":
            errors.append(f"a machine of kind {auto.kind!r} has an ε edge from {q!r}")
        if len(dsts) > 1 and auto.kind == "dfa":
            errors.append(f"a DFA has {len(dsts)} targets for ({q!r}, {a!r})")
    return errors


def has_epsilon(auto: Automaton) -> bool:
    return any(a == EPS for _, a in auto.delta)


def is_complete_dfa(auto: Automaton) -> bool:
    """True if `auto` is a DFA with exactly one target for every state and symbol."""
    return auto.kind == "dfa" and all(
        len(auto.targets(q, a)) == 1 for q in auto.states for a in auto.alphabet
    )


def display_symbol(a: str) -> str:
    return EPS_LABEL if a == EPS else a


def canonical_json(value: object) -> str:
    """The one serialisation used for every hash (CLAUDE.md item 4)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def model_hash(auto: Automaton) -> str:
    """SHA-256 of the canonical JSON of (Q, Σ, δ, q₀, F); metadata is excluded (spec §10.3)."""
    payload = {
        "Q": sorted(auto.states),
        "Sigma": sorted(auto.alphabet),
        "delta": sorted(
            [q, display_symbol(a), sorted(dsts)] for (q, a), dsts in auto.delta.items()
        ),
        "q0": auto.start,
        "F": sorted(auto.final),
    }
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def reachable(auto: Automaton) -> frozenset[str]:
    """States reachable from q₀ over any label, ε included."""
    successors: dict[str, set[str]] = {}
    for (q, _), dsts in auto.delta.items():
        successors.setdefault(q, set()).update(dsts)
    seen = {auto.start}
    queue = deque([auto.start])
    while queue:
        for r in successors.get(queue.popleft(), ()):
            if r not in seen:
                seen.add(r)
                queue.append(r)
    return frozenset(seen)


def dead_states(auto: Automaton) -> frozenset[str]:
    """States from which no accepting state can be reached."""
    predecessors: dict[str, set[str]] = {}
    for (q, _), dsts in auto.delta.items():
        for r in dsts:
            predecessors.setdefault(r, set()).add(q)
    alive = set(auto.final)
    queue = deque(auto.final)
    while queue:
        for p in predecessors.get(queue.popleft(), ()):
            if p not in alive:
                alive.add(p)
                queue.append(p)
    return frozenset(auto.states) - alive


def trim(auto: Automaton) -> Automaton:
    """Drop unreachable states and record the dead ones (CLAUDE.md item 5).

    Dead states stay in the model so complement DFAs remain complete; the views hide them.
    """
    keep = reachable(auto)
    trimmed = replace(
        auto,
        states=tuple(q for q in auto.states if q in keep),
        delta={(q, a): dsts for (q, a), dsts in auto.delta.items() if q in keep},
        final=auto.final & keep,
        meanings={q: m for q, m in auto.meanings.items() if q in keep},
        dead=frozenset(),
    )
    return replace(trimmed, dead=dead_states(trimmed))
