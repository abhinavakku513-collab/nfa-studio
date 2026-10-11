"""Recognising requests for non-regular languages (spec §6.4).

Detection is rule-based and cannot be complete; anything it misses is stopped by the
compiler's limits and by verification.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Final


@dataclass(frozen=True)
class Alternative:
    """A regular language close to what was asked for, as text and, when exact, as IR."""

    text: str
    ir: dict[str, object] | None = None


class NonRegularRequest(Exception):
    code: ClassVar[str] = "E_UNSUPPORTED_NONREGULAR"

    def __init__(self, reason: str, why: str, alternative: Alternative) -> None:
        super().__init__(f"This language is not regular: it {why}. {alternative.text}")
        self.reason = reason
        self.why = why
        self.alternative = alternative


@dataclass(frozen=True)
class _Rule:
    reason: str
    pattern: re.Pattern[str]
    why: str
    alternative: Callable[[re.Match[str]], Alternative]
    # The alternative without a matched phrase to quote, for a family the LLM tier names.
    general: str


def _power_words(symbols: tuple[str, ...], bound: int) -> Alternative:
    shown = "".join(f"{s}ⁿ" for s in symbols)
    words = ["".join(s * n for s in symbols) for n in range(bound + 1)]
    return Alternative(
        f"Try {shown} with n ≤ {bound}, a finite union, which is regular.",
        {
            "ir_version": "1.0",
            "alphabet": {"symbols": sorted(set(symbols)), "source": "user"},
            "language": {"type": "literal_set", "words": words},
        },
    )


_COUNTING: Final = "needs to count without a bound"

_RULES: Final = (
    _Rule(
        "power_counting",
        re.compile(r"(\w)\^n\s*(\w)\^n(?:\s*(\w)\^n)?"),
        _COUNTING,
        # Four repetitions keep the longest word within the pattern-length limit.
        lambda m: _power_words(tuple(s for s in m.groups() if s), 4),
        "Try a bounded version such as aⁿbⁿ with n ≤ 4, a finite union, which is regular.",
    ),
    _Rule(
        "equal_counts",
        re.compile(
            r"\b(?:(?:same|equal) (?:number|count|amount)s? of (?P<x>\S+?)(?:'s|s)? and "
            r"(?P<y>\S+?)(?:'s|s)?|as many (?P<x2>\S+?)(?:'s|s)? as (?P<y2>\S+?)(?:'s|s)?)"
            r"(?:\s|$)"
        ),
        _COUNTING,
        lambda m: Alternative(
            f"Try a bounded version: the numbers of {m['x'] or m['x2']}'s and "
            f"{m['y'] or m['y2']}'s differ by at most k, or both are at most k, for a fixed k."
        ),
        "Try a bounded version: the two counts differ by at most k, or both are at most k, "
        "for a fixed k.",
    ),
    _Rule(
        "more_than",
        re.compile(
            r"\b(?:more|fewer|less) (?P<x>(?!than\b)\S+?)(?:'s|s)? "
            r"than (?P<y>\S+?)(?:'s|s)?(?:\s|$)"
        ),
        _COUNTING,
        lambda m: Alternative(
            f"Try a bounded version: the difference between the numbers of {m['x']}'s and "
            f"{m['y']}'s is at most k, for a fixed k."
        ),
        "Try a bounded version: the difference between the two counts is at most k, for a fixed k.",
    ),
    _Rule(
        "palindrome",
        re.compile(r"\bpalindrom|\brevers(?:e|al)|\bof the form w\s*w\b|\bww\b"),
        "needs unbounded memory of what was read",
        lambda m: Alternative("Try palindromes (or ww) up to a fixed length k, a finite set."),
        "Try palindromes (or ww) up to a fixed length k, a finite set.",
    ),
    _Rule(
        "length_not_periodic",
        re.compile(
            r"\bprime\b|\bperfect square|\bsquare number|\bfactorial|\bpower of (?:two|2)\b"
        ),
        "describes a set of lengths that is not ultimately periodic",
        lambda m: Alternative("Try lengths from a stated finite set, or a length mod m condition."),
        "Try lengths from a stated finite set, or a length mod m condition.",
    ),
    _Rule(
        "balanced_brackets",
        re.compile(
            r"\bbalanced\b|\bwell[- ]formed\b|\bmatching (?:paren|bracket)|\bnested\b|\bdyck\b"
        ),
        "is context-free, not regular: brackets may nest without a bound",
        lambda m: Alternative("Try balanced brackets with nesting depth at most k, for a fixed k."),
        "Try balanced brackets with nesting depth at most k, for a fixed k.",
    ),
)


REASONS: Final = tuple(rule.reason for rule in _RULES)


def refusal(reason: str) -> NonRegularRequest:
    """The refusal for a family named by reason; an unknown one gets a general answer."""
    for rule in _RULES:
        if rule.reason == reason:
            return NonRegularRequest(reason, rule.why, Alternative(rule.general))
    return NonRegularRequest(
        "not_regular",
        "needs memory that grows with the input",
        Alternative("Try a bounded version: limit the length or the counts to a fixed k."),
    )


def check_nonregular(text: str) -> None:
    """Raise NonRegularRequest if `text` (normalised) asks for a known non-regular family."""
    lowered = text.lower()
    for rule in _RULES:
        if match := rule.pattern.search(lowered):
            raise NonRegularRequest(rule.reason, rule.why, rule.alternative(match))
