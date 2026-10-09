"""The ambiguity taxonomy (spec §6.2, CLAUDE.md C4, C13).

A question is asked only when its answer changes the language. Each unanswered
choice is left in the draft IR as a `Hole` holding the exact value every option
stands for, so an answer is merged, not re-interpreted.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from nfa_studio.ir.limits import LIMITS

Topic = Literal["count_exact_or_at_least", "overlap", "grouping", "alphabet"]


@dataclass(frozen=True)
class Option:
    id: str
    label: str


EDIT_OPTION: Final = Option("edit", "Edit manually")


@dataclass(frozen=True, eq=False)
class Hole:
    """An open choice in a draft; `values[option id]` is what that answer fills in."""

    topic: Topic
    text: str
    options: tuple[Option, ...]
    values: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, eq=False)
class Lazy:
    """A draft value that depends on the alphabet, which may itself still be a question."""

    make: Callable[[tuple[str, ...]], object]


def count_hole(what: str, n: int) -> Hole:
    """'contains two a's': exactly or at least? (spec §6.2)."""
    return Hole(
        "count_exact_or_at_least",
        f"Exactly {n} {what}, or at least {n}?",
        (Option("exactly", f"Exactly {n}"), Option("at_least", f"At least {n}")),
        {"exactly": "eq", "at_least": "ge"},
    )


def border(pattern: str) -> int:
    """Length of the longest proper border: a non-empty prefix that is also a suffix."""
    return max((k for k in range(1, len(pattern)) if pattern[:k] == pattern[-k:]), default=0)


def overlap_hole(pattern: str) -> Hole | None:
    """Ask about overlap only if the pattern can overlap itself (C4); otherwise None."""
    k = border(pattern)
    if k == 0:
        return None
    example = pattern + pattern[k:]
    return Hole(
        "overlap",
        f"May the occurrences of {pattern} overlap (as in {example})?",
        (Option("yes", "Yes, overlap allowed"), Option("no", "No, they must be disjoint")),
        {"yes": True, "no": False},
    )


def grouping_hole(readings: list[tuple[str, object]]) -> Hole:
    """'a or b followed by c', or mixed and/or: which grouping is meant?"""
    options = tuple(Option(f"g{i}", label) for i, (label, _) in enumerate(readings, start=1))
    return Hole(
        "grouping",
        "Which grouping do you mean?",
        options,
        {option.id: tree for option, (_, tree) in zip(options, readings, strict=True)},
    )


def alphabet_hole(inferred: tuple[str, ...]) -> Hole:
    """Asked only when the wording hints at more symbols than it mentions (spec §6.2)."""
    wider = _with_next_symbol(inferred)
    readings = [("mentioned", inferred), ("wider", wider)] if wider else [("mentioned", inferred)]
    options = tuple(Option(key, "{" + ", ".join(symbols) + "}") for key, symbols in readings)
    return Hole(
        "alphabet",
        "Which symbols can the strings use?",
        options,
        {key: list(symbols) for key, symbols in readings},
    )


def _with_next_symbol(symbols: tuple[str, ...]) -> tuple[str, ...] | None:
    last = symbols[-1]
    if not last.isalnum() or len(symbols) >= LIMITS.max_alphabet_size:
        return None
    following = chr(ord(last) + 1)
    if not following.isalnum() or following in symbols:
        return None
    return (*symbols, following)
