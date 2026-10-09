"""Text → draft IR: non-regular check, then the rule parser (spec §6).

The optional LLM tier (Phase 6) plugs in where the rule parser gives up or reports
low confidence; everything it returns goes through the same validation.
"""

from nfa_studio.interpret.nonregular import check_nonregular
from nfa_studio.interpret.rule_parser import Draft, normalize, parse


def interpret(text: str) -> Draft:
    """Read a description; raises NonRegularRequest, UnsupportedRequest or AlphabetMissing."""
    normalized = normalize(text)
    check_nonregular(normalized)
    return parse(normalized)
