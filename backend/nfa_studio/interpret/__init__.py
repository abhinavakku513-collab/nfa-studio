"""Text → draft IR: non-regular check, the rule parser, then the optional LLM tier (spec §6)."""

import logging

from nfa_studio.interpret.llm_adapter import LLMTier, LLMUnavailable
from nfa_studio.interpret.nonregular import check_nonregular
from nfa_studio.interpret.rule_parser import (
    CONFIDENCE_THRESHOLD,
    Draft,
    UnsupportedRequest,
    normalize,
    parse,
)

logger = logging.getLogger("nfa_studio.interpret")


def interpret(text: str, llm: LLMTier | None = None) -> Draft:
    """Read a description; raises NonRegularRequest, UnsupportedRequest or AlphabetMissing.

    The LLM tier is asked only when the rules cannot read the text or read it with
    confidence below the threshold (spec §6.1). Refusals the rules are sure of, such
    as non-regular requests, never reach it.
    """
    normalized = normalize(text)
    check_nonregular(normalized)
    try:
        draft = parse(normalized)
    except UnsupportedRequest as exc:
        if llm is None or exc.reason != "not_interpretable":
            raise
        return _ask_model(llm, normalized, exc, confidence=0.0)
    if llm is None or draft.confidence >= CONFIDENCE_THRESHOLD:
        return draft
    return _ask_model(llm, normalized, draft, confidence=draft.confidence)


def _ask_model(
    llm: LLMTier, normalized: str, rules: Draft | UnsupportedRequest, confidence: float
) -> Draft:
    try:
        return llm.interpret(normalized, confidence)
    except LLMUnavailable as exc:
        # The model could not be asked; answer as the rules alone would have.
        logger.warning("LLM tier unavailable, using the rules alone: %s", exc)
        if isinstance(rules, Draft):
            return rules
        raise rules from None
