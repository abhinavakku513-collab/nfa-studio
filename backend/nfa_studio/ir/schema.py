"""Language Specification IR: the closed node catalogue and the document shape (spec §5).

Field-level limits come from `LIMITS`. Rules that need the whole document (alphabet
rules, symbol membership, node count) live in `normalize`.
"""

from typing import Annotated, Final, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nfa_studio.ir.limits import LIMITS, Limits

IR_VERSION: Final = "1.0"

Pattern = Annotated[str, Field(min_length=1, max_length=LIMITS.max_pattern_len)]
Symbol = Annotated[str, Field(min_length=1, max_length=1)]
Count = Annotated[int, Field(ge=0, le=LIMITS.max_count)]
CountOp = Literal["eq", "ge", "le"]


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StartsWith(_Node):
    type: Literal["starts_with"] = "starts_with"
    pattern: Pattern


class EndsWith(_Node):
    type: Literal["ends_with"] = "ends_with"
    pattern: Pattern


class Contains(_Node):
    type: Literal["contains"] = "contains"
    pattern: Pattern


class Avoids(_Node):
    type: Literal["avoids"] = "avoids"
    pattern: Pattern


class SymbolCount(_Node):
    type: Literal["symbol_count"] = "symbol_count"
    symbol: Symbol
    op: CountOp
    n: Count


class SymbolParity(_Node):
    type: Literal["symbol_parity"] = "symbol_parity"
    symbol: Symbol
    parity: Literal["even", "odd"]


class LengthMod(_Node):
    type: Literal["length_mod"] = "length_mod"
    # The modulus sizes the automaton like a count does, so it shares the count limit.
    m: Annotated[int, Field(ge=1, le=LIMITS.max_count)]
    r: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _remainder_below_modulus(self) -> "LengthMod":
        if self.r >= self.m:
            raise ValueError(f"r must be less than m (got m={self.m}, r={self.r})")
        return self


class PatternCount(_Node):
    type: Literal["pattern_count"] = "pattern_count"
    pattern: Pattern
    op: CountOp
    n: Count
    # spec §5.1: overlap must be explicit, so there is no default.
    overlap: bool


class Regex(_Node):
    type: Literal["regex"] = "regex"
    expr: Annotated[str, Field(min_length=1, max_length=LIMITS.max_regex_len)]


class LiteralSet(_Node):
    type: Literal["literal_set"] = "literal_set"
    # "" is the empty word ε.
    words: Annotated[
        tuple[Annotated[str, Field(max_length=LIMITS.max_pattern_len)], ...],
        Field(min_length=1, max_length=LIMITS.max_count),
    ]


class And(_Node):
    type: Literal["and"] = "and"
    children: Annotated[tuple["Node", ...], Field(min_length=1)]


class Or(_Node):
    type: Literal["or"] = "or"
    children: Annotated[tuple["Node", ...], Field(min_length=1)]


class Not(_Node):
    type: Literal["not"] = "not"
    child: "Node"


class Concat(_Node):
    type: Literal["concat"] = "concat"
    children: Annotated[tuple["Node", ...], Field(min_length=1)]


class Star(_Node):
    type: Literal["star"] = "star"
    child: "Node"


Node: TypeAlias = Annotated[
    StartsWith
    | EndsWith
    | Contains
    | Avoids
    | SymbolCount
    | SymbolParity
    | LengthMod
    | PatternCount
    | Regex
    | LiteralSet
    | And
    | Or
    | Not
    | Concat
    | Star,
    Field(discriminator="type"),
]

for _model in (And, Or, Not, Concat, Star):
    _model.model_rebuild()

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


class Alphabet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbols: tuple[str, ...]
    source: Literal["user", "inferred", "default"]


class Assumption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text: str
    editable: bool


class Clarification(BaseModel):
    """A clarification question that was answered (spec §6.3, CLAUDE.md C13)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: Literal["count_exact_or_at_least", "overlap", "grouping", "alphabet"]
    answer: str


class IRDocument(BaseModel):
    """A full LSIR document (spec §5.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ir_version: Literal["1.0"] = IR_VERSION
    alphabet: Alphabet
    language: Node
    assumptions: tuple[Assumption, ...] = ()
    clarifications: tuple[Clarification, ...] = ()
    # Echoed for clients; normalisation always replaces it with the server's limits.
    limits: Limits = LIMITS
