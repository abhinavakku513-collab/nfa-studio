"""Tier-1 interpreter: phrase rules over a normalised sentence (spec §6.1).

The sentence is normalised, its alphabet clause is taken out, and the rest is read as
one clause or as clauses joined by and/or/but. Each clause must match a lexicon rule
completely; nothing is guessed from a partial match. The result is a draft IR whose
open choices are `Hole`s and whose alphabet-dependent parts are `Lazy`.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import ClassVar, Final

from nfa_studio.interpret import lexicon as lx
from nfa_studio.interpret.ambiguity import (
    Lazy,
    alphabet_hole,
    count_hole,
    grouping_hole,
    overlap_hole,
)
from nfa_studio.ir.schema import IR_VERSION

# Confidence lost for each clause that had to borrow its predicate from the one before
# ("ending with ab or ba"). Below the threshold the optional LLM tier takes over.
ELLIPSIS_PENALTY: Final = 0.1
CONFIDENCE_THRESHOLD: Final = 0.7


class UnsupportedRequest(Exception):
    """Regular, perhaps, but not expressible here, or not readable at all (C11)."""

    code: ClassVar[str] = "E_UNSUPPORTED_FEATURE"

    def __init__(self, reason: str, message: str, examples: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.reason = reason
        self.examples = examples


class AlphabetMissing(Exception):
    code: ClassVar[str] = "E_ALPHABET_MISSING"

    def __init__(self) -> None:
        super().__init__(
            "The description names no symbols, so no alphabet can be inferred. "
            "Add one, for example 'over {a,b}'."
        )


@dataclass(frozen=True)
class Clause:
    """One parsed condition: its IR (with holes and lazy parts) and the symbols it names."""

    tree: object
    symbols: str
    assumptions: tuple[str, ...] = ()
    # The same predicate applied to another pattern, for "ending with ab or ba".
    respell: Callable[[str], "Clause"] | None = None


@dataclass(frozen=True)
class Draft:
    ir: dict[str, object]
    confidence: float


_TRANSLATION: Final = str.maketrans(
    {
        "ⁿ": "^n",
        "ᵐ": "^m",
        "ᵏ": "^k",
        "ⁱ": "^i",
        **{sup: f"^{d}" for d, sup in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")},
        # Curly and low single quotes, then double quotes.
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "–": "-",
        "—": "-",
        "≤": " at most ",
        "≥": " at least ",
    }
)


def normalize(text: str) -> str:
    """Superscripts become ^n (aⁿbⁿ → a^nb^n), curly quotes straight, then NFKC.

    Whitespace is collapsed and closing punctuation dropped. Case is kept, because
    symbols are case-sensitive.
    """
    text = unicodedata.normalize("NFKC", text.translate(_TRANSLATION))
    return re.sub(r"[.!?]+$", "", re.sub(r"\s+", " ", text).strip()).strip()


def tokenize(text: str) -> list[str]:
    """Items of a list such as 'a, b' or '"0" or 10', with quotes and braces removed."""
    pieces = re.split(r"\s*,\s*|\s+(?:or|and)\s+|\s+", text.strip().strip("{}"))
    return [p.strip("'\"{}") for p in pieces if p.strip("'\"{}")]


def parse(text: str) -> Draft:
    """Read a normalised description into a draft IR, or raise why it cannot be read."""
    _refuse_numeric_value(text)
    explicit, rest = _explicit_alphabet(text)
    binary = re.search(r"\bbinary\b", rest, re.I) is not None
    hinted = re.search(lx.ALPHABET_HINTS, rest, re.I) is not None
    body = re.sub(_HINT_PHRASE, "", rest, flags=re.I).strip()
    clause, confidence = _parse_body(re.sub(r"\s+", " ", body))
    symbols, source, assumption = _alphabet(explicit, binary, set(clause.symbols), hinted)
    ids = list(dict.fromkeys((*clause.assumptions, *assumption)))
    return Draft(
        {
            "ir_version": IR_VERSION,
            "alphabet": {"symbols": symbols, "source": source},
            "language": clause.tree,
            "assumptions": [
                {"id": i, "text": lx.ASSUMPTIONS[i][0], "editable": lx.ASSUMPTIONS[i][1]}
                for i in ids
            ],
            "clarifications": [],
        },
        confidence,
    )


_NUMERIC_VALUE: Final = re.compile(r"\b(?:binary |decimal |natural )?numbers?\b(?! of\b)", re.I)
_ARITHMETIC: Final = re.compile(r"\b(?:divisible|multiple|value|greater|smaller|prime)\b", re.I)


def _refuse_numeric_value(text: str) -> None:
    if _NUMERIC_VALUE.search(text) and _ARITHMETIC.search(text):
        raise UnsupportedRequest(
            "numeric_value",
            "Conditions on the number a string represents are regular, but the "
            "specification language has no node for numeric values. Describe the strings "
            "by their symbols instead, for example 'binary strings ending in 0'.",
        )


_EXPLICIT: Final = re.compile(
    r"\s*(?:\b(?:over|on)\s+(?:the\s+)?(?:alphabet\s+)?|\balphabet\s+|Σ\s*=\s*)"
    r"(?:Σ\s*=\s*)?\{(?P<set>[^{}]*)\}",
    re.I,
)


def _explicit_alphabet(text: str) -> tuple[list[str] | None, str]:
    match = _EXPLICIT.search(text)
    if match is None:
        return None, text
    rest = text[: match.start()].rstrip(" ,") + " " + text[match.end() :].lstrip(" ,")
    rest = rest.strip()
    return tokenize(match["set"]), re.sub(r"\s+", " ", rest)


_HINT_PHRASE: Final = r"\s*\b(?:over|using|with) (?:the |any )?(?:letters|characters|symbols)\b"


def _alphabet(
    explicit: list[str] | None, binary: bool, mentioned: set[str], hinted: bool
) -> tuple[object, str, tuple[str, ...]]:
    """C5: explicit set; else binary, then 0/1 or a/b, then the symbols mentioned."""
    if explicit is not None:
        return explicit, "user", ()
    if binary or (mentioned and mentioned <= {"0", "1"}):
        inferred: tuple[str, ...] = ("0", "1")
    elif not mentioned:
        raise AlphabetMissing()
    elif mentioned <= {"a", "b"}:
        inferred = ("a", "b")
    else:
        inferred = tuple(sorted(mentioned))
        if len(inferred) == 1 and inferred[0] in lx.PARTNERS:
            inferred = tuple(sorted({inferred[0], lx.PARTNERS[inferred[0]]}))
    value: object = alphabet_hole(inferred) if hinted else list(inferred)
    return value, "inferred", ("alphabet_inferred",)


def _parse_body(body: str) -> tuple[Clause, float]:
    if (whole := _clause(body)) is not None:
        return whole, 1.0
    pieces = re.split(lx.CONNECTIVE, body, flags=re.I)
    parts, joins = pieces[0::2], ["or" if j.lower() == "or" else "and" for j in pieces[1::2]]
    # "strings that start with a and ...": the part before the first "that" names nothing.
    while joins and not _strip_filler(parts[0]):
        parts, joins = parts[1:], joins[1:]
    if not joins:
        raise _not_interpretable(body)
    clauses: list[Clause] = []
    confidence = 1.0
    for part in parts:
        clause = _clause(part)
        bare = re.fullmatch(r"['\"]?([^\s'\"]+)['\"]?", part.strip())
        if clause is None and bare and clauses and clauses[-1].respell is not None:
            clause = clauses[-1].respell(bare[1])
            confidence -= ELLIPSIS_PENALTY
        if clause is None:
            raise _not_interpretable(body)
        clauses.append(clause)
    if len(set(joins)) == 1:
        return _join(joins[0], clauses), confidence
    # Mixed and/or: the grouping changes the language, so it is asked (spec §6.2).
    left, left_text = clauses[0], parts[0]
    for join, clause, text in zip(joins, clauses[1:], parts[1:], strict=True):
        left, left_text = _join(join, [left, clause]), f"({left_text} {join} {text})"
    right, right_text = clauses[-1], parts[-1]
    for join, clause, text in zip(
        reversed(joins), reversed(clauses[:-1]), reversed(parts[:-1]), strict=True
    ):
        right, right_text = _join(join, [clause, right]), f"({text} {join} {right_text})"
    hole = grouping_hole([(left_text[1:-1], left.tree), (right_text[1:-1], right.tree)])
    return _merged(hole, clauses), confidence


def _join(op: str, clauses: list[Clause]) -> Clause:
    return _merged({"type": op, "children": [c.tree for c in clauses]}, clauses)


def _merged(tree: object, clauses: list[Clause]) -> Clause:
    return Clause(
        tree,
        "".join(c.symbols for c in clauses),
        tuple(a for c in clauses for a in c.assumptions),
    )


def _not_interpretable(text: str) -> UnsupportedRequest:
    examples = "; ".join(f"'{e}'" for e in lx.EXAMPLE_PROMPTS)
    return UnsupportedRequest(
        "not_interpretable",
        f"Could not read '{text}' as a description of strings. Use phrases such as "
        f"'starts with', 'ends with', 'contains' or 'even number of', for example {examples}.",
        lx.EXAMPLE_PROMPTS,
    )


def _strip_filler(text: str) -> str:
    return re.sub(lx.LEADING_FILLER, "", text.strip() + " ", flags=re.I).strip()


def _clause(text: str) -> Clause | None:
    text = _strip_filler(text)
    negation = re.match(lx.NEGATION, text, re.I)
    if negation:
        text = text[negation.end() :]
    for candidate in dict.fromkeys((text, re.sub(r"^(?:has|have|having|with)\s+", "", text))):
        for pattern, handler in _RULES:
            if (match := pattern.fullmatch(candidate)) and (clause := handler(match)):
                return _negate(clause) if negation else clause
    return None


def _negate(clause: Clause) -> Clause:
    tree = clause.tree
    if isinstance(tree, dict) and tree.get("type") == "contains":
        # "does not contain p" is avoids(p), which compiles to a direct KMP DFA (spec §7.2).
        negated: object = {"type": "avoids", "pattern": tree["pattern"]}
    else:
        negated = {"type": "not", "child": tree}
    original = clause.respell
    if original is None:
        return replace(clause, tree=negated, respell=None)

    def respell(pattern: str) -> Clause:
        return _negate(original(pattern))

    return replace(clause, tree=negated, respell=respell)


def _number(text: str) -> int:
    return int(text) if text.isdigit() else lx.NUMBER_WORDS[text.lower()]


def _literal(*words: str) -> dict[str, object]:
    return {"type": "literal_set", "words": list(words)}


def _concat(parts: list[object]) -> object:
    return parts[0] if len(parts) == 1 else {"type": "concat", "children": parts}


ANY_SYMBOL: Final = Lazy(lambda alphabet: _literal(*alphabet))
ANY_SYMBOL_OR_NONE: Final = Lazy(lambda alphabet: _literal("", *alphabet))
ANYTHING: Final = {"type": "star", "child": ANY_SYMBOL}


def _predicate(kind: str) -> Callable[[str], Clause]:
    def make(pattern: str) -> Clause:
        return Clause({"type": kind, "pattern": pattern}, pattern, respell=make)

    return make


def _count(what: str, op: str | None, n: int, plural: str) -> Clause:
    """A count of one symbol, or of a longer pattern with the overlap rule of C4.

    `op` None means the wording left exactly/at least open, so it is asked (spec §6.2).
    """
    asked: object = count_hole(plural, n) if op is None else op
    if len(what) == 1:
        return Clause({"type": "symbol_count", "symbol": what, "op": asked, "n": n}, what)
    overlap = overlap_hole(what)
    tree = {
        "type": "pattern_count",
        "pattern": what,
        "op": asked,
        "n": n,
        "overlap": overlap if overlap is not None else False,
    }
    return Clause(tree, what, () if overlap else ("no_overlap_possible",))


def _qualified(q: str, n: str) -> tuple[str, int]:
    op, shift = lx.QUALIFIERS[q.lower()]
    return op, _number(n) + shift


def _length(op: str, n: int) -> Clause:
    if op == "eq":
        tree = _concat([ANY_SYMBOL] * n) if n else _literal("")
    elif op == "le":
        tree = _concat([ANY_SYMBOL_OR_NONE] * n) if n else _literal("")
    else:
        tree = _concat([*[ANY_SYMBOL] * n, ANYTHING])
    return Clause(tree, "")


def _kth(k: int, symbol: str, from_end: bool) -> Clause:
    if k == 1:
        return _predicate("ends_with" if from_end else "starts_with")(symbol)
    fill = [ANY_SYMBOL] * (k - 1)
    parts = [ANYTHING, _literal(symbol), *fill] if from_end else [*fill, _literal(symbol), ANYTHING]
    return Clause(_concat(parts), symbol)


def _ordinal(text: str) -> int:
    lowered = text.lower()
    return lx.ORDINAL_WORDS.get(lowered) or int(re.sub(r"\D", "", lowered))


def _every_next(first: str, second: str, preceded: bool) -> Clause:
    pair = second + first if preceded else first + second

    def tree(alphabet: tuple[str, ...]) -> object:
        return {"type": "star", "child": _literal(*(a for a in alphabet if a != first), pair)}

    return Clause(Lazy(tree), first + second)


def _same_ends() -> Clause:
    def tree(alphabet: tuple[str, ...]) -> object:
        return {
            "type": "or",
            "children": [
                {
                    "type": "and",
                    "children": [
                        {"type": "starts_with", "pattern": a},
                        {"type": "ends_with", "pattern": a},
                    ],
                }
                for a in alphabet
            ],
        }

    return Clause(Lazy(tree), "", ("same_symbol_nonempty",))


def _words(listing: str) -> Clause | None:
    empty = {"ε", "epsilon", "empty", "the empty string", "the empty word"}
    items = re.split(r"\s*,\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and\s+", listing.strip().strip("{}"))
    words = ["" if w.strip("'\"").lower() in empty else w.strip("'\"") for w in items if w.strip()]
    if not words or any(" " in w for w in words):
        return None
    return Clause(_literal(*words), "".join(words))


def _regex(expr: str) -> Clause | None:
    if not set(expr) & set("()|*+?ε"):
        return None
    return Clause({"type": "regex", "expr": expr}, "".join(c for c in expr if c not in "()|*+?ε"))


def _grouping(a: str, b: str, c: str) -> Clause:
    hole = grouping_hole(
        [
            (f"({a} or {b}) then {c}", _literal(a + c, b + c)),
            (f"{a}, or {b} then {c}", _literal(a, b + c)),
        ]
    )
    return Clause(hole, a + b + c)


def _p(name: str = "p") -> str:
    return rf"['\"]?(?P<{name}>[^\s,;'\"]+)['\"]?"


def _s(name: str = "s") -> str:
    return rf"['\"]?(?P<{name}>[^\s'\"])['\"]?(?:'s|s)?"


def _n(name: str = "n") -> str:
    return rf"(?P<{name}>{lx.NUMBER})"


_Q: Final = rf"(?P<q>{lx.QUALIFIER})"
_OCCURRENCES: Final = r"(?:occurrences?|instances?|copies|appearances?) of"
_TIMES: Final = rf"(?P<times>once|twice|thrice|{_n('k')} times)"

Handler = Callable[[re.Match[str]], Clause | None]

_RULE_TABLE: Final[list[tuple[str, Handler]]] = [
    # spec §6.2: "a or b followed by c" has two readings.
    (rf"{_p('a')} or {_p('b')} followed by {_p('c')}", lambda m: _grouping(m["a"], m["b"], m["c"])),
    (
        r"(?:starts?|starting|begins?|beginning) and (?:ends?|ending) "
        rf"with the same {lx.SYMBOL_NOUN}"
        rf"|(?:the )?first and last {lx.SYMBOL_NOUN}s? (?:are|is) (?:the )?same"
        rf"|(?:(?:has|have|having|with) )?the same first and last {lx.SYMBOL_NOUN}",
        lambda m: _same_ends(),
    ),
    (
        rf"(?:starts?|starting|begins?|beginning) (?:with|in) (?:the (?:substring|prefix) )?{_p()}",
        lambda m: _predicate("starts_with")(m["p"]),
    ),
    (
        r"(?:ends?|ending|finish(?:es)?|finishing) (?:with|in) "
        rf"(?:the (?:substring|suffix) )?{_p()}",
        lambda m: _predicate("ends_with")(m["p"]),
    ),
    (rf"no {_n()} (?:consecutive {_s()}|{_s('s2')} in a row)", lambda m: _consecutive(m)),
    (
        rf"(?:without|avoiding|avoids?) (?:the )?(?:substring |pattern |factor )?{_p()}",
        lambda m: _predicate("avoids")(m["p"]),
    ),
    (
        rf"(?:an? )?(?P<par>even|odd) (?:number|count|amount) of {_s()}"
        rf"|{_s('s2')} (?:appears?|occurs?) an? (?P<par2>even|odd) number of times"
        rf"|(?:the )?(?:number|count) of {_s('s3')} is (?P<par3>even|odd)",
        lambda m: Clause(
            {
                "type": "symbol_parity",
                "symbol": m["s"] or m["s2"] or m["s3"],
                "parity": (m["par"] or m["par2"] or m["par3"]).lower(),
            },
            m["s"] or m["s2"] or m["s3"],
            ("zero_is_even",),
        ),
    ),
    (
        rf"(?:{lx.HAVE} )?{_Q} {_n()} (?:{_OCCURRENCES} {_p()}|{_s()})",
        lambda m: _count(m["p"] or m["s"], *_qualified(m["q"], m["n"]), "occurrences"),
    ),
    (
        rf"{lx.HAVE} {_n()} (?:{_OCCURRENCES} {_p()}|{_s()})",
        lambda m: _count(
            m["p"] or m["s"],
            None,
            _number(m["n"]),
            f"occurrences of {m['p']}" if m["p"] else f"{m['s']}'s",
        ),
    ),
    (
        rf"(?:{lx.HAVE} )?{_p()} (?:(?P<q>exactly|at least|at most) )?{_TIMES}",
        lambda m: _count(
            m["p"],
            "ge" if m["q"] is None else lx.QUALIFIERS[m["q"].lower()][0],
            lx.TIMES_WORDS.get((m["times"] or "").lower()) or _number(m["k"]),
            "occurrences",
        ),
    ),
    (
        r"(?:(?:of|with|having|has|have) )?(?:an? )?(?P<par>even|odd) length"
        r"|(?:the )?length (?:is )?(?P<par2>even|odd)",
        lambda m: _length_parity((m["par"] or m["par2"]).lower()),
    ),
    (
        rf"(?:the )?(?:length|size) (?:that )?(?:is )?(?:divisible by|a multiple of) {_n('m')}",
        lambda m: Clause(
            {"type": "length_mod", "m": _number(m["m"]), "r": 0}, "", ("length_includes_empty",)
        ),
    ),
    (
        rf"(?:the )?length (?:is )?(?:congruent to )?{_n('r')} (?:mod|modulo) {_n('m')}",
        lambda m: Clause({"type": "length_mod", "m": _number(m["m"]), "r": _number(m["r"])}, ""),
    ),
    (
        rf"(?:of )?(?:a )?length (?:is )?(?:(?:{_Q}|exactly|equal to) )?{_n()}",
        lambda m: _length(*(_qualified(m["q"], m["n"]) if m["q"] else ("eq", _number(m["n"])))),
    ),
    (
        rf"(?:the )?(?P<k>{lx.ORDINAL}) {lx.SYMBOL_NOUN}"
        r"(?P<end> from the (?:end|right)| from last)?"
        rf"(?: from the (?:start|left|beginning))? (?:is|equals|=) {_s()}",
        lambda m: _kth(_ordinal(m["k"]), m["s"], m["end"] is not None),
    ),
    (
        rf"(?:the )?(?:(?P<k>{lx.ORDINAL})[- ]to[- ]last|(?P<last>last|final)) {lx.SYMBOL_NOUN} "
        rf"(?:is|equals|=) {_s()}",
        lambda m: _kth(_ordinal(m["k"]) if m["k"] else 1, m["s"], True),
    ),
    (
        rf"(?:every|each) {_s('x')} is (?:immediately |directly )?"
        rf"(?P<rel>followed|preceded) by {_s('y')}",
        lambda m: _every_next(m["x"], m["y"], m["rel"].lower() == "preceded"),
    ),
    (
        r"(?:(?:equal to|exactly|in the set|either) )?one of:? (?P<list>.+)",
        lambda m: _words(m["list"]),
    ),
    (
        rf"{lx.HAVE} {_p()} as an? (?:substring|subword|factor|infix)",
        lambda m: _predicate("contains")(m["p"]),
    ),
    (
        rf"{lx.HAVE} (?:the |an? )?(?:substring |subword |factor |pattern |string )?{_p()}",
        lambda m: _predicate("contains")(m["p"]),
    ),
    (
        r"(?:(?:matching|matches|matched by|described by|generated by|given by|of the form) )?"
        r"(?:the )?(?:regex |regular expression |expression )?(?P<r>[^\s]+)",
        lambda m: _regex(m["r"]),
    ),
]


def _consecutive(m: re.Match[str]) -> Clause:
    return Clause(
        {"type": "avoids", "pattern": (m["s"] or m["s2"]) * _number(m["n"])},
        m["s"] or m["s2"],
        ("avoids_consecutive",),
    )


def _length_parity(parity: str) -> Clause:
    if parity == "even":
        return Clause({"type": "length_mod", "m": 2, "r": 0}, "", ("length_includes_empty",))
    return Clause({"type": "length_mod", "m": 2, "r": 1}, "")


_RULES: Final = [(re.compile(pattern, re.I), handler) for pattern, handler in _RULE_TABLE]
