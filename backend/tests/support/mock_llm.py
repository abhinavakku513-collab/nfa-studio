"""A stand-in for the model, so no test needs the network or an API key."""

import json
from typing import Any

from nfa_studio.interpret.llm_adapter import LLMTier

DECLINE = json.dumps({"error": "not_expressible", "reason": "stand-in"})


def reading(language: dict[str, Any], symbols: str, source: str = "inferred") -> str:
    """A reply holding an LSIR document, as a well-behaved model would send it."""
    return json.dumps(
        {
            "ir_version": "1.0",
            "alphabet": {"symbols": list(symbols), "source": source},
            "language": language,
            "assumptions": [],
        }
    )


def not_regular(kind: str) -> str:
    return json.dumps({"error": "not_regular", "kind": kind, "reason": "stand-in"})


class MockModel:
    """Replies from a table by normalised description, declining anything else."""

    def __init__(self, replies: dict[str, str] | None = None, default: str = DECLINE) -> None:
        self.replies = dict(replies or {})
        self.default = default
        self.calls: list[str] = []

    def __call__(self, system: str, text: str) -> str:
        self.calls.append(text)
        return self.replies.get(text, self.default)

    def tier(self) -> LLMTier:
        return LLMTier(self)
