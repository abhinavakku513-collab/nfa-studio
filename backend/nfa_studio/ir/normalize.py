"""Validation, normalisation and the specification hash of LSIR documents (spec §5.3)."""

import hashlib
from collections.abc import Iterator
from typing import ClassVar, Final, assert_never

from pydantic import ValidationError

from nfa_studio.core.model import EPS_LABEL, canonical_json
from nfa_studio.ir.limits import LIMITS
from nfa_studio.ir.schema import (
    Alphabet,
    And,
    Avoids,
    Concat,
    Contains,
    EndsWith,
    IRDocument,
    LengthMod,
    LiteralSet,
    Node,
    Not,
    Or,
    PatternCount,
    Regex,
    Star,
    StartsWith,
    SymbolCount,
    SymbolParity,
)

# CLAUDE.md item 3: these collide with regex syntax or with ε itself.
RESERVED_SYMBOLS: Final = frozenset("()|*+?\\" + EPS_LABEL)
REGEX_SYNTAX: Final = frozenset("()|*+?" + EPS_LABEL)


class IRInvalid(Exception):
    code: ClassVar[str] = "E_SCHEMA_INVALID"

    def __init__(self, errors: list[str]) -> None:
        super().__init__("The specification is invalid: " + "; ".join(errors))
        self.errors = tuple(errors)


def validate_ir(data: object) -> IRDocument:
    """Parse untrusted IR (from rules, an LLM or a client) and normalise it."""
    try:
        doc = IRDocument.model_validate(data)
    except ValidationError as exc:
        raise IRInvalid(
            [f"{'.'.join(map(str, e['loc'])) or 'document'}: {e['msg']}" for e in exc.errors()]
        ) from exc
    return normalize(doc)


def normalize(doc: IRDocument) -> IRDocument:
    """Apply the §5.3 rules; the result is canonical, so normalising twice changes nothing.

    The alphabet is sorted and deduplicated and checked against CLAUDE.md item 3;
    nested and/or are flattened, double negation is removed, and/or children are
    sorted by node type, then canonical JSON; single-child and/or/concat are unwrapped and
    literal_set words are sorted and deduplicated. Symbols stay case-sensitive.
    """
    symbols = _normalize_alphabet(doc.alphabet.symbols)
    errors = []
    nodes = sum(1 for _ in _walk(doc.language))
    if nodes > LIMITS.max_nodes:
        errors.append(f"the IR has {nodes} nodes; the limit is {LIMITS.max_nodes}")
    errors.extend(_symbol_errors(doc.language, symbols))
    if errors:
        raise IRInvalid(errors)
    return doc.model_copy(
        update={
            "alphabet": Alphabet(symbols=symbols, source=doc.alphabet.source),
            "language": _normalize_node(doc.language),
            "limits": LIMITS,
        }
    )


def spec_hash(doc: IRDocument) -> str:
    """SHA-256 of the canonical JSON of what determines the language: version, Σ and tree.

    Assumption texts, clarification records and source labels do not change the
    language, so they are left out and equal languages share one cache entry.
    """
    payload = {
        "ir_version": doc.ir_version,
        "alphabet": list(doc.alphabet.symbols),
        "language": doc.language.model_dump(mode="json"),
    }
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _normalize_alphabet(raw: tuple[str, ...]) -> tuple[str, ...]:
    errors = []
    for s in raw:
        if len(s) != 1:
            errors.append(f"alphabet symbol {s!r} must be exactly one character")
        elif not s.isprintable() or s.isspace():
            errors.append(f"alphabet symbol {s!r} must be a printable non-whitespace character")
        elif s in RESERVED_SYMBOLS:
            errors.append(f"alphabet symbol {s!r} is reserved for regex syntax or ε")
    symbols = tuple(sorted(set(raw)))
    if not LIMITS.min_alphabet_size <= len(symbols) <= LIMITS.max_alphabet_size:
        errors.append(
            f"the alphabet has {len(symbols)} symbols; it needs "
            f"{LIMITS.min_alphabet_size} to {LIMITS.max_alphabet_size}"
        )
    if errors:
        raise IRInvalid(errors)
    return symbols


def _walk(node: Node) -> Iterator[Node]:
    yield node
    match node:
        case And(children=children) | Or(children=children) | Concat(children=children):
            for child in children:
                yield from _walk(child)
        case Not(child=child) | Star(child=child):
            yield from _walk(child)


def _used_symbols(node: Node) -> str:
    match node:
        case StartsWith(pattern=p) | EndsWith(pattern=p) | Contains(pattern=p) | Avoids(pattern=p):
            return p
        case PatternCount(pattern=p):
            return p
        case SymbolCount(symbol=s) | SymbolParity(symbol=s):
            return s
        case Regex(expr=expr):
            return "".join(c for c in expr if c not in REGEX_SYNTAX)
        case LiteralSet(words=words):
            return "".join(words)
        case LengthMod() | And() | Or() | Not() | Concat() | Star():
            return ""
        case _:
            assert_never(node)


def _symbol_errors(language: Node, alphabet: tuple[str, ...]) -> Iterator[str]:
    allowed = set(alphabet)
    for node in _walk(language):
        for s in sorted(set(_used_symbols(node)) - allowed):
            yield (f"symbol {s!r} in {node.type} is not in the alphabet {{{', '.join(alphabet)}}}")


def _normalize_node(node: Node) -> Node:
    match node:
        case And(children=children) | Or(children=children):
            kind = type(node)
            flat: list[Node] = []
            for child in map(_normalize_node, children):
                flat.extend(child.children if isinstance(child, kind) else (child,))
            if len(flat) == 1:
                return flat[0]
            # Node type first keeps like constraints together when the IR is read back.
            flat.sort(key=lambda child: (child.type, canonical_json(child.model_dump(mode="json"))))
            return kind(children=tuple(flat))
        case Not(child=child):
            inner = _normalize_node(child)
            return inner.child if isinstance(inner, Not) else Not(child=inner)
        case Concat(children=children):
            parts = tuple(map(_normalize_node, children))
            return parts[0] if len(parts) == 1 else Concat(children=parts)
        case Star(child=child):
            return Star(child=_normalize_node(child))
        case LiteralSet(words=words):
            return LiteralSet(words=tuple(sorted(set(words))))
        case _:
            return node
