"""The verification ladder V0–V3 (spec §8.2, CLAUDE.md C8, C9)."""

import random
from collections import OrderedDict
from dataclasses import dataclass
from typing import ClassVar, Final, Literal

from nfa_studio.core.closure import eclose, step
from nfa_studio.core.determinize import negate, remove_epsilon
from nfa_studio.core.model import (
    EPS_LABEL,
    Automaton,
    has_epsilon,
    model_hash,
    structural_errors,
)
from nfa_studio.core.simulate import accepts
from nfa_studio.ir.limits import LIMITS, Budget, StateLimitExceeded, TimeBudgetExceeded
from nfa_studio.ir.normalize import normalize, spec_hash, walk
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import IRDocument, Node, Not
from nfa_studio.reference.equivalence import language_difference
from nfa_studio.reference.to_dfa import NotTranslatable, reference_dfa
from nfa_studio.render import RenderMismatch, ensure_consistent
from nfa_studio.render.json_graph import diagram_graph
from nfa_studio.render.table import build_table

Level = Literal["V0", "V1", "V2", "V3"]
Badge = Literal["grey", "amber", "green"]

BADGES: Final[dict[Level, Badge]] = {"V0": "grey", "V1": "amber", "V2": "green"}
NO_REFERENCE_NOTE: Final = (
    "pattern_count has no reference translation yet, so this machine is checked against "
    "the oracle only: bounded and property tests, not exact equivalence."
)
REFERENCE_LIMIT_NOTE: Final = (
    "The exact check stopped at its limit (2,000 states or the time budget), so "
    "equivalence with the reference was not decided."
)
_CACHE_SIZE: Final = 1024


class VerificationFailed(Exception):
    """The automaton is wrong; it must not be shown (spec §8.2)."""

    code: ClassVar[str] = "E_VERIFY_FAILED"

    def __init__(self, level: Level, problem: str, counterexample: str | None = None) -> None:
        super().__init__(f"{level} failed: {problem}")
        self.level = level
        self.counterexample = counterexample


@dataclass(frozen=True)
class Check:
    level: Level
    evidence: str


@dataclass(frozen=True)
class Report:
    """Every check that passed, the strongest exact-or-bounded level and its badge colour."""

    automaton_id: str
    level: Level
    badge: Badge
    checks: tuple[Check, ...]
    bounded_length: int
    property_runs: int
    notes: tuple[str, ...]


_cache: OrderedDict[tuple[str, str], Report] = OrderedDict()


def verify(auto: Automaton, doc: IRDocument) -> Report:
    """Run V0–V3 for `auto` against the specification `doc`; raise VerificationFailed.

    Results are cached by automaton id together with the specification hash: the same
    machine checked against a different specification is a different question.
    """
    doc = normalize(doc)
    automaton_id = model_hash(auto)
    key = (automaton_id, spec_hash(doc))
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    report = _climb(auto, doc, automaton_id)
    _cache[key] = report
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return report


def bounded_length(alphabet_size: int) -> int:
    """C8: the largest L ≤ 10 with Σ_{k=0..L} |Σ|^k ≤ 200 000."""
    total, length = 1, 0
    while length < LIMITS.bounded_max_length:
        total += alphabet_size ** (length + 1)
        if total > LIMITS.bounded_max_words:
            break
        length += 1
    return length


def _climb(auto: Automaton, doc: IRDocument, automaton_id: str) -> Report:
    language = doc.language
    checks: list[Check] = []
    notes: list[str] = []

    # V0: structure. The model refuses malformed machines at construction, so this
    # re-checks it, that the machine speaks the specification's alphabet, and that the
    # table and diagram regenerate from δ with the automaton's hash.
    errors = structural_errors(auto)
    if auto.alphabet != doc.alphabet.symbols:
        errors.append(f"Σ is {auto.alphabet}, the specification's is {doc.alphabet.symbols}")
    try:
        views = (build_table(auto, show_dead=True), diagram_graph(auto, show_dead=True))
        ensure_consistent(automaton_id, *views)
    except RenderMismatch as exc:
        errors.append(str(exc))
    if errors:
        raise VerificationFailed("V0", "; ".join(errors))
    checks.append(Check("V0", "Well-formed"))

    length = bounded_length(len(auto.alphabet))
    word = _bounded_counterexample(auto, language, length)
    if word is not None:
        raise VerificationFailed("V1", _disagreement(auto, word, matches(language, word)), word)
    checks.append(Check("V1", f"Verified on all strings up to length {length}"))

    level: Level = "V1"
    budget = Budget(max_states=LIMITS.reference_max_states)
    try:
        reference = reference_dfa(doc, budget)
        word = language_difference(auto, reference, budget)
    except NotTranslatable:
        notes.append(NO_REFERENCE_NOTE)
    except (StateLimitExceeded, TimeBudgetExceeded):
        notes.append(REFERENCE_LIMIT_NOTE)
    else:
        if word is not None:
            expected = accepts(reference, word)
            problem = _disagreement(auto, word, expected, "the reference DFA")
            raise VerificationFailed("V2", problem, word)
        checks.append(Check("V2", "Exactly equivalent to reference"))
        level = "V2"

    runs = _property_tests(auto, language, automaton_id, notes)
    checks.append(Check("V3", f"Property tests passed ({runs} runs)"))
    return Report(automaton_id, level, BADGES[level], tuple(checks), length, runs, tuple(notes))


def _bounded_counterexample(auto: Automaton, language: Node, length: int) -> str | None:
    """The shortest word up to `length` where automaton and oracle disagree (C8).

    Depth-first over the word tree in alphabet order, carrying the active set from
    parent to child instead of re-simulating each word. Below a disagreement, and
    at or beyond the length of the best one found, nothing shorter can appear.
    """
    found: str | None = None
    moves: dict[tuple[frozenset[str], str], frozenset[str]] = {}
    stack = [("", eclose(auto, (auto.start,)))]
    while stack:
        word, active = stack.pop()
        if bool(active & auto.final) != matches(language, word):
            if found is None or len(word) < len(found):
                found = word
            continue
        if len(word) == length or (found is not None and len(word) + 1 >= len(found)):
            continue
        for a in reversed(auto.alphabet):
            key = (active, a)
            if key not in moves:
                moves[key] = step(auto, active, a)
            stack.append((word + a, moves[key]))
    return found


def _property_tests(auto: Automaton, language: Node, automaton_id: str, notes: list[str]) -> int:
    """V3 at runtime (C9): random words against the oracle, then closure laws.

    The words are drawn from a generator seeded by the automaton id, so a report can
    be reproduced. Mutation testing lives in the test suite, not here.
    """
    rnd = random.Random(int(automaton_id.removeprefix("sha256:")[:16], 16))
    runs = 0
    for _ in range(LIMITS.property_words):
        size = rnd.randint(0, LIMITS.property_max_length)
        word = "".join(rnd.choice(auto.alphabet) for _ in range(size))
        expected = matches(language, word)
        if accepts(auto, word) != expected:
            raise VerificationFailed("V3", _disagreement(auto, word, expected), word)
        runs += 1

    laws: list[tuple[str, Automaton]] = []
    budget = Budget(max_states=LIMITS.reference_max_states)
    try:
        if any(isinstance(node, Not) for node in walk(language)):
            laws.append(("the double complement", negate(negate(auto, budget), budget)))
        if has_epsilon(auto):
            laws.append(("the ε-free view", remove_epsilon(auto)))
        for name, other in laws:
            difference = language_difference(other, auto, budget)
            if difference is not None:
                problem = f"{name} differs from the machine on {_show(difference)}"
                raise VerificationFailed("V3", problem, difference)
            runs += 1
    except (StateLimitExceeded, TimeBudgetExceeded):
        notes.append("Some closure-law checks stopped at their limit and were skipped.")
    return runs


def _disagreement(
    auto: Automaton, word: str, expected: bool, source: str = "the specification"
) -> str:
    actual = "accepts" if accepts(auto, word) else "rejects"
    wanted = "accepts" if expected else "rejects"
    return f"the automaton {actual} {_show(word)}, but {source} {wanted} it"


def _show(word: str) -> str:
    return repr(word) if word else EPS_LABEL
