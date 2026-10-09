"""Language Specification IR (spec §5)."""

from typing import Final

IR_VERSION: Final = "1.0"

# spec §5.1: the closed node catalogue; anything else is rejected by validation.
NODE_TYPES: Final = (
    "starts_with",
    "ends_with",
    "contains",
    "avoids",
    "symbol_count",
    "symbol_parity",
    "length_mod",
    "pattern_count",
    "regex",
    "literal_set",
    "and",
    "or",
    "not",
    "concat",
    "star",
)
