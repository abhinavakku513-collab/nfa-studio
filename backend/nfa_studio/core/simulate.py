"""Set-based simulation with a full trace and a witness path (spec §9, CLAUDE.md C1, C2)."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import ClassVar

from nfa_studio.core.closure import eclose, eclose_with_pred, step
from nfa_studio.core.model import EPS, Automaton, Edge
from nfa_studio.ir.limits import LIMITS


class SymbolNotInAlphabet(Exception):
    code: ClassVar[str] = "E_SYMBOL_NOT_IN_ALPHABET"

    def __init__(self, symbol: str, position: int, alphabet: tuple[str, ...]) -> None:
        super().__init__(
            f"{symbol!r} at position {position} is not in the alphabet "
            f"{{{', '.join(alphabet)}}}. Use only these symbols."
        )
        self.symbol = symbol
        self.position = position


class InputTooLong(Exception):
    code: ClassVar[str] = "E_INPUT_TOO_LONG"

    def __init__(self, length: int, limit: int) -> None:
        super().__init__(
            f"The input has {length} symbols; the limit is {limit}. Use a shorter word."
        )
        self.length = length
        self.limit = limit


@dataclass(frozen=True)
class Step:
    """One row of the trace (spec §9.2 plus `transitions` and `epsilon_layers` from C2).

    Index 0 is the initial ε-closure of {q₀}; index i ≥ 1 has consumed symbol i.
    State sets are in naming order. `final_accepted` is set only on the last step.
    """

    index: int
    symbol: str | None
    moved: tuple[str, ...]
    after: tuple[str, ...]
    accepting_present: bool
    final_accepted: bool | None
    transitions: tuple[Edge, ...]
    epsilon_layers: tuple[tuple[Edge, ...], ...]


@dataclass(frozen=True)
class Trace:
    word: str
    steps: tuple[Step, ...]
    accepted: bool
    witness: tuple[Edge, ...] | None


def check_word(auto: Automaton, word: str) -> None:
    """Raise InputTooLong or SymbolNotInAlphabet (1-based position) for an unusable word."""
    if len(word) > LIMITS.max_word_len:
        raise InputTooLong(len(word), LIMITS.max_word_len)
    alphabet = set(auto.alphabet)
    for position, a in enumerate(word, start=1):
        if a not in alphabet:
            raise SymbolNotInAlphabet(a, position, auto.alphabet)


def accepts(auto: Automaton, word: str) -> bool:
    """Acceptance only, using the memoised closures."""
    check_word(auto, word)
    active = eclose(auto, (auto.start,))
    for a in word:
        active = step(auto, active, a)
    return bool(active & auto.final)


def simulate(auto: Automaton, word: str, witness: bool = True) -> Trace:
    """Run `word` on `auto`, recording every active set; passing through F early never accepts."""
    check_word(auto, word)
    closure = eclose_with_pred(auto, (auto.start,))
    preds: list[Mapping[str, tuple[str, str]]] = [closure.pred]
    steps = [
        Step(
            index=0,
            symbol=None,
            moved=(auto.start,),
            after=auto.ordered(closure.states),
            accepting_present=bool(closure.states & auto.final),
            final_accepted=None,
            transitions=(),
            epsilon_layers=closure.layers,
        )
    ]
    for i, a in enumerate(word, start=1):
        transitions = tuple(
            (q, a, r) for q in steps[-1].after for r in auto.ordered(auto.targets(q, a))
        )
        # C1: a state reached by several edges keeps the first source in naming order.
        pred: dict[str, tuple[str, str]] = {}
        for q, _, r in transitions:
            pred.setdefault(r, (q, a))
        moved = auto.ordered(pred)
        closure = eclose_with_pred(auto, moved)
        pred.update(closure.pred)
        preds.append(pred)
        steps.append(
            Step(
                index=i,
                symbol=a,
                moved=moved,
                after=auto.ordered(closure.states),
                accepting_present=bool(closure.states & auto.final),
                final_accepted=None,
                transitions=transitions,
                epsilon_layers=closure.layers,
            )
        )
    accepted = steps[-1].accepting_present
    steps[-1] = replace(steps[-1], final_accepted=accepted)
    path = _witness(auto, steps[-1].after, preds) if witness and accepted else None
    return Trace(word, tuple(steps), accepted, path)


def _witness(
    auto: Automaton, final_active: tuple[str, ...], preds: list[Mapping[str, tuple[str, str]]]
) -> tuple[Edge, ...]:
    """Follow predecessor pointers back from the lowest-named accepting state (C1).

    Within a step, ε predecessors lead back through the closure to a state entered by
    a symbol edge, whose predecessor lies in the previous step's active set. At step
    0 the ε chain ends at q₀.
    """
    q = next(r for r in final_active if r in auto.final)
    path: list[Edge] = []
    for pred in reversed(preds):
        while q in pred:
            prev, label = pred[q]
            path.append((prev, label, q))
            q = prev
            if label != EPS:
                break
    if q != auto.start:
        raise AssertionError(f"witness reconstruction ended at {q!r}, not at q₀")
    return tuple(reversed(path))
