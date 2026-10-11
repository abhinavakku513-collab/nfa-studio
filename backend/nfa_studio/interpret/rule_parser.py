"""Tier-1 interpreter: phrase rules over a normalised sentence (spec §6.1).

The sentence is normalised, its alphabet clause is taken out, and the rest is read as
one clause or as clauses joined by and/or/but. Each clause must match a lexicon rule
completely; nothing is guessed from a partial match. The result is a draft IR whose
open choices are `Hole`s and whose alphabet-dependent parts are `Lazy`.
"""

import difflib
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
# Confidence lost for each word whose spelling had to be corrected before it could be read.
SPELLING_PENALTY: Final = 0.1


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
    """A parsed description; `confidence` says how fully the rules read the text."""

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


_QUOTES: Final = "'\"`\u201c\u201d\u2018\u2019"
_TRAILING: Final = re.compile(rf"[\s.,;:!?{_QUOTES}]+$")
_LEADING: Final = re.compile(rf"^[\s{_QUOTES}]+")


def tidy(text: str) -> str:
    """Quotes and stray punctuation around a description, and brackets that wrap all of it.

    A pattern keeps its quotes inside the sentence ("contains 'ab' twice"); only the
    ends are trimmed, and the rules accept a pattern whose closing quote went with them.
    Brackets go only when they wrap a whole sentence, so a regex such as (ab) is kept.
    """
    while True:
        tidied = _LEADING.sub("", _TRAILING.sub("", text))
        if _wrapped(tidied):
            tidied = tidied[1:-1]
        if tidied == text:
            return text
        text = tidied


def _wrapped(text: str) -> bool:
    """True if `text` is one ( … ) or [ … ] around words, not a regex group."""
    pairs = {"(": ")", "[": "]"}
    if len(text) < 2 or pairs.get(text[0]) != text[-1] or " " not in text:
        return False
    depth = 0
    for i, char in enumerate(text):
        depth += (char == text[0]) - (char == text[-1])
        if depth == 0 and i < len(text) - 1:
            return False
    return True


def strip_lead_in(text: str) -> str:
    """Command words and the like before the description, however many and in any order."""
    while True:
        stripped = tidy(re.sub(lx.LEAD_IN, "", tidy(text), count=1, flags=re.I))
        if stripped == text:
            return text
        text = stripped


def tokenize(text: str) -> list[str]:
    """Items of a list such as 'a, b' or '"0" or 10', with quotes and braces removed."""
    pieces = re.split(r"\s*,\s*|\s+(?:or|and)\s+|\s+", text.strip().strip("{}"))
    return [p.strip("'\"{}") for p in pieces if p.strip("'\"{}")]


def parse(text: str) -> Draft:
    """Read a normalised description into a draft IR, or raise why it cannot be read."""
    _refuse_numeric_value(text)
    explicit, rest = _explicit_alphabet(text)
    rest = strip_lead_in(rest)
    fixes: tuple[tuple[str, str], ...] = ()
    try:
        clause, confidence, binary, hinted = _read(rest)
    except _Unread as unread:
        # Only a description that cannot be read as typed is read again with its
        # spelling corrected, so a readable one never changes.
        respelled, fixes = _correct_spelling(rest, explicit)
        if not fixes:
            raise _refusal(unread, explicit, rest) from None
        try:
            clause, confidence, binary, hinted = _read(respelled)
        except _Unread:
            raise _refusal(unread, explicit, rest) from None
        confidence -= SPELLING_PENALTY * len(fixes)
    symbols, source, assumption = _alphabet(explicit, binary, set(clause.symbols), hinted)
    ids = list(dict.fromkeys((*clause.assumptions, *assumption)))
    assumptions = [
        {"id": i, "text": lx.ASSUMPTIONS[i][0], "editable": lx.ASSUMPTIONS[i][1]} for i in ids
    ]
    if fixes:
        respellings = ", ".join(f"'{typed}' as '{word}'" for typed, word in fixes)
        assumptions.append(
            {"id": "spelling_corrected", "text": f"Read {respellings}.", "editable": False}
        )
    return Draft(
        {
            "ir_version": IR_VERSION,
            "alphabet": {"symbols": symbols, "source": source},
            "language": clause.tree,
            "assumptions": assumptions,
            "clarifications": [],
        },
        confidence,
    )


_BINARY: Final = re.compile(r"\b(?:binary|bit[- ]?strings?|bitstrings?)\b", re.I)
# "an even number of zeros", "at least 3 ones": digits named as words. "ones" only after
# a count word or "of", so "the ones that end in 0" keeps its meaning.
_ZEROS: Final = re.compile(r"\bzeroe?s\b", re.I)
_ONES: Final = re.compile(
    rf"\b(\d+|{'|'.join(lx.NUMBER_WORDS)}|of|many|more|fewer|less|least|most) ones\b", re.I
)


def _digit_words(text: str) -> str:
    return _ONES.sub(r"\1 1s", _ZEROS.sub("0s", text))


def _read(rest: str) -> tuple[Clause, float, bool, bool]:
    """The description without its alphabet: its clause, confidence and alphabet hints."""
    rest = _digit_words(rest)
    binary = _BINARY.search(rest) is not None
    hinted = re.search(lx.ALPHABET_HINTS, rest, re.I) is not None
    body = re.sub(_HINT_PHRASE, "", rest, flags=re.I).strip()
    clause, confidence = _parse_body(re.sub(r"\s+", " ", body))
    return clause, confidence, binary, hinted


def _refusal(unread: "_Unread", explicit: list[str] | None, rest: str) -> UnsupportedRequest:
    binary = _BINARY.search(rest) is not None
    alphabet = explicit if explicit is not None else (["0", "1"] if binary else None)
    understood = (
        *([f"the alphabet {{{', '.join(alphabet)}}}"] if alphabet else []),
        *(f'"{part}"' for part in unread.understood),
    )
    return not_interpretable(unread.text, understood=understood, whole=rest)


def _correct_spelling(
    text: str, alphabet: list[str] | None
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Misspelled vocabulary ("statr", "endign") as the closest known word.

    Only words of five or more letters, with three or more distinct letters and not
    made of alphabet symbols alone, are candidates, so patterns such as abba are kept.
    """
    symbols = set(alphabet or ())
    fixes: list[tuple[str, str]] = []

    def fix(match: re.Match[str]) -> str:
        word = match[0]
        lowered = word.lower()
        if lowered in lx.VOCABULARY or len(set(lowered)) < 3 or set(word) <= symbols:
            return word
        close = difflib.get_close_matches(lowered, lx.VOCABULARY, n=1, cutoff=0.8)
        if not close:
            return word
        fixes.append((word, close[0]))
        return close[0]

    return re.sub(r"\b[A-Za-z]{5,}\b", fix, text), tuple(fixes)


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


_NAMED: Final = r"(?:Σ|\b[A-Za-z])\s*=\s*"
# Brackets are tolerated as typed: {0,1}, [0,1], {[0,1] and an unclosed {0,1 all name {0,1}.
_EXPLICIT: Final = re.compile(
    rf"\s*(?:(?:\b(?:over|on)\s+(?:the\s+)?(?:alphabet\s+)?|\balphabet\s+)(?:{_NAMED})?|{_NAMED})"
    r"[{\[]+\s*(?P<set>[^\s,{}\[\]]+(?:\s*,\s*[^\s,{}\[\]]+)*)\s*[}\]]*",
    re.I,
)
# "over 0 and 1", "over a, b and c": single symbols listed without braces.
_LISTED: Final = re.compile(
    r"\s*\b(?:over|on)\s+(?:the\s+)?(?:symbols\s+|digits\s+|letters\s+)?"
    r"(?P<set>[0-9A-Za-z](?:\s*,\s*[0-9A-Za-z])*,?\s+(?:and|or)\s+[0-9A-Za-z])(?=[\s,]|$)",
    re.I,
)


# "strings of a's and b's", "words made of 0s and 1s": only the "of …" part is cut.
_MADE_OF: Final = re.compile(
    r"\b(?:strings?|words?|sequences?)(?P<cut>\s+(?:made\s+(?:up\s+)?)?of\s+"
    r"(?P<set>[0-9A-Za-z](?:'s|s)?(?:\s*,\s*[0-9A-Za-z](?:'s|s)?)*,?\s+(?:and|or)\s+"
    r"[0-9A-Za-z](?:'s|s)?))(?=[\s,]|$)",
    re.I,
)


def _explicit_alphabet(text: str) -> tuple[list[str] | None, str]:
    if made_of := _MADE_OF.search(text):
        items = re.split(r"\s*,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+", made_of["set"])
        symbols = [item[0] for item in items]
        rest = text[: made_of.start("cut")] + text[made_of.end("cut") :]
        return symbols, re.sub(r"\s+", " ", rest).strip()
    match = _EXPLICIT.search(text) or _LISTED.search(text)
    if match is None:
        return None, text
    rest = text[: match.start()].rstrip(" ,") + " " + text[match.end() :].lstrip(" ,:")
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


class _Unread(Exception):
    """A part no rule reads, and the conditions read before it."""

    def __init__(self, text: str, understood: tuple[str, ...] = ()) -> None:
        super().__init__(text)
        self.text = text
        self.understood = understood


def _parse_body(body: str) -> tuple[Clause, float]:
    """Clauses joined by and/or, with "and" binding tighter: a and b or c is (a and b) or c."""
    if (whole := _clause(body)) is not None:
        return whole, 1.0
    pieces = re.split(lx.CONNECTIVE, body, flags=re.I)
    parts, joins = pieces[0::2], ["or" if j.lower() == "or" else "and" for j in pieces[1::2]]
    # "strings that start with a and ...": the part before the first "that" names nothing.
    while joins and not _strip_filler(parts[0]):
        parts, joins = parts[1:], joins[1:]
    if not joins:
        raise _Unread(body)
    first = _clause(parts[0])
    if first is None:
        raise _Unread(parts[0].strip())
    terms, term_joins = [first], []
    read = [_strip_filler(parts[0])]
    confidence = 1.0
    for join, part in zip(joins, parts[1:], strict=True):
        clause = _clause(part)
        bare = re.fullmatch(r"['\"]?([^\s'\"]+)['\"]?", part.strip())
        if clause is None and bare and terms[-1].respell is not None:
            # "ending with ab or ba": the bare pattern borrows the predicate before it and
            # stays with it, ahead of any and/or grouping around the pair.
            confidence -= ELLIPSIS_PENALTY
            respelled = terms[-1].respell(bare[1])
            terms[-1] = replace(_join(join, [terms[-1], respelled]), respell=terms[-1].respell)
            read[-1] += f" {join} {bare[1]}"
            continue
        if clause is None:
            raise _Unread(part.strip(), tuple(read))
        terms.append(clause)
        term_joins.append(join)
        read.append(_strip_filler(part))
    alternatives = [[terms[0]]]
    for join, term in zip(term_joins, terms[1:], strict=True):
        if join == "or":
            alternatives.append([term])
        else:
            alternatives[-1].append(term)
    conjunctions = [group[0] if len(group) == 1 else _join("and", group) for group in alternatives]
    if len(conjunctions) == 1:
        return conjunctions[0], confidence
    return _join("or", conjunctions), confidence


def _join(op: str, clauses: list[Clause]) -> Clause:
    """An and/or node; children of the same operator are flattened into it."""
    children: list[object] = []
    for clause in clauses:
        tree = clause.tree
        if isinstance(tree, dict) and tree.get("type") == op:
            children.extend(tree["children"])
        else:
            children.append(tree)
    return _merged({"type": op, "children": children}, clauses)


def _merged(tree: object, clauses: list[Clause]) -> Clause:
    return Clause(
        tree,
        "".join(c.symbols for c in clauses),
        tuple(a for c in clauses for a in c.assumptions),
    )


def not_interpretable(
    text: str, also: str = "", understood: tuple[str, ...] = (), whole: str | None = None
) -> UnsupportedRequest:
    """C11's refusal: what was read, the part that was not, and the closest example first.

    `also` adds why, such as the language model's verdict; the example closest to the
    `whole` description, when given, is suggested rather than the one closest to `text`.
    """
    examples = closest_examples(whole or text)
    if understood:
        read = f"I read {_listing(understood)}, but couldn't find a condition in"
    else:
        read = "I couldn't find a condition in"
    return UnsupportedRequest(
        "not_interpretable",
        f"{read} \"{text}\"{also}. Describe the strings with phrases such as 'starts with', "
        f"'ends with', 'contains' or 'even number of'; the closest example is "
        f"'{examples[0]}'.",
        examples,
    )


_NOT_CONTENT: Final = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "binary",
        "by",
        "in",
        "is",
        "no",
        "of",
        "or",
        "over",
        "string",
        "that",
        "the",
        "whose",
        "with",
        "word",
    ]
)


def closest_examples(text: str) -> tuple[str, ...]:
    """Three readable examples, the one sharing most content words with `text` first.

    Ties keep the catalogue order, so with nothing in common the usual first example leads.
    """

    def words(phrase: str) -> set[str]:
        stems = {re.sub(r"(?:ing|es|s)$", "", w) for w in re.findall(r"\w+", phrase.lower())}
        return stems - _NOT_CONTENT

    asked = words(text)

    def closeness(example: str) -> float:
        shared = asked & words(example)
        return len(shared) / len(asked | words(example)) if shared else 0.0

    closest = max(lx.EXAMPLE_CATALOG, key=closeness)
    return (closest, *(e for e in lx.EXAMPLE_PROMPTS if e != closest))[:3]


def _listing(items: tuple[str, ...]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


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
    if len(what) > 1 and (op, n) == ("ge", 1):
        # At least one occurrence: overlap cannot matter, so this is plain containment.
        return _predicate("contains")(what)
    if len(what) > 1 and n == 0 and op in ("eq", "le"):
        return _predicate("avoids")(what)
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
# "begins with a 1": an article before a pattern; "begins with a" keeps its symbol.
_ARTICLE: Final = r"(?:(?:an?|the) (?=\S))?"
_ITEM: Final = r"['\"]?[^\s,{}'\"]+['\"]?"
# Two or more words joined by commas, "and" or "or", or a braced list of any length.
_LIST: Final = (
    rf"\{{?\s*{_ITEM}(?:\s*,\s*(?:(?:and|or)\s+)?{_ITEM}|\s+(?:and|or)\s+{_ITEM})+\s*\}}?"
    rf"|\{{\s*{_ITEM}(?:\s*,\s*{_ITEM})*\s*\}}"
)


def _fixed_end(kind: str, m: re.Match[str]) -> Clause | None:
    """starts_with/ends_with; "the first two symbols are ab" must name that many."""
    pattern = m["p"] or m["p2"] or m["p3"]
    if m["k"] and _number(m["k"]) != len(pattern):
        return None
    return _predicate(kind)(pattern)


def _repetition(pattern: str, at_least_once: bool) -> Clause:
    star = {"type": "star", "child": _literal(pattern)}
    return Clause(_concat([_literal(pattern), star]) if at_least_once else star, pattern)


def _every_kth(k: int, symbol: str) -> Clause:
    """Positions k, 2k, 3k, … hold `symbol`: (Σ^(k-1) s)*, then fewer than k symbols."""
    block = _concat([*[ANY_SYMBOL] * (k - 1), _literal(symbol)])
    tail = _concat([ANY_SYMBOL_OR_NONE] * (k - 1)) if k > 1 else _literal("")
    return Clause(_concat([{"type": "star", "child": block}, tail]), symbol)


def _none_of(pattern: str) -> Clause:
    """ "no 11", "no a's": the pattern never occurs."""
    return _predicate("avoids")(pattern[:-2] if pattern.endswith("'s") else pattern)


def _length_between(low: int, high: int) -> Clause | None:
    if low > high:
        return None
    return Clause(_concat([*[ANY_SYMBOL] * low, *[ANY_SYMBOL_OR_NONE] * (high - low)]), "")


def _then_repeated(first: str, repeated: str, at_least_once: bool) -> Clause:
    """ "a 1 followed by any number of 0s": first, then repeated zero or more times."""
    tail = _repetition(repeated, at_least_once)
    return Clause(_concat([_literal(first), tail.tree]), first + repeated)


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
        r"(?:starts?|starting|begins?|beginning) and (?:ends?|ending) (?:with|in) "
        rf"{_ARTICLE}{_p()}",
        lambda m: _join(
            "and", [_predicate("starts_with")(m["p"]), _predicate("ends_with")(m["p"])]
        ),
    ),
    (
        rf"(?:starts?|starting|started|begins?|beginning|began|begun) (?:with|in) "
        rf"(?:the (?:substring|prefix) )?{_ARTICLE}{_p()}"
        rf"|(?:(?:with|having|has) )?(?:the |a )?prefix {_p('p2')}"
        rf"|(?:the )?first (?:{_n('k')} )?{lx.SYMBOL_NOUN}s? (?:are|is) {_p('p3')}",
        lambda m: _fixed_end("starts_with", m),
    ),
    (
        r"(?:ends?|ending|ended|finish(?:es|ed|ing)?) (?:with|in) "
        rf"(?:the (?:substring|suffix) )?{_ARTICLE}{_p()}"
        rf"|(?:(?:with|having|has) )?(?:the |a )?suffix {_p('p2')}"
        rf"|(?:the )?last (?:{_n('k')} )?{lx.SYMBOL_NOUN}s? (?:are|is) {_p('p3')}",
        lambda m: _fixed_end("ends_with", m),
    ),
    (rf"no {_n()} (?:consecutive {_s()}|{_s('s2')} in a row)", lambda m: _consecutive(m)),
    (
        rf"(?:{lx.HAVE} )?{_n()} (?:consecutive {_s()}|{_s('s2')} in a row)",
        lambda m: _predicate("contains")((m["s"] or m["s2"]) * _number(m["n"])),
    ),
    (
        rf"{_s('x')} (?:never|does not|doesn't|doesnt) (?:comes?|appears?|occurs?) "
        rf"(?:right |immediately |directly )?(?P<rel>after|before) {_ARTICLE}{_s('y')}",
        lambda m: _predicate("avoids")(
            m["y"] + m["x"] if m["rel"].lower() == "after" else m["x"] + m["y"]
        ),
    ),
    (
        rf"(?:without|avoiding|avoids?|free of) (?:the )?(?:substring |pattern |factor )?{_p()}"
        rf"|{_p('p2')} (?:does not|doesn't|doesnt|never) (?:appears?|occurs?)",
        lambda m: _predicate("avoids")(m["p"] or m["p2"]),
    ),
    (
        r"(?:(?:with|having|has|have|contains?|containing) )?no "
        rf"(?:substring |occurrences? of |copies of )?{_p()}",
        lambda m: _none_of(m["p"]),
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
        # "copies of ab" here would be repetition, as in "one or more copies of ab".
        rf"(?:{lx.HAVE} )?{_n()} or (?P<dir>more|fewer|less) "
        rf"(?:(?:occurrences?|instances?|appearances?) of {_p()}|{_s()})",
        lambda m: _count(
            m["p"] or m["s"],
            "ge" if m["dir"].lower() == "more" else "le",
            _number(m["n"]),
            "occurrences",
        ),
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
        rf"(?:the )?(?:number|count) of {_s()} is (?:(?:{_Q}|exactly|equal to) )?{_n()}",
        lambda m: _count(
            m["s"],
            *(_qualified(m["q"], m["n"]) if m["q"] else ("eq", _number(m["n"]))),
            "occurrences",
        ),
    ),
    (
        rf"(?:{lx.HAVE} )?{_p()} (?:(?:appears?|occurs?) )?(?:(?P<q>exactly|at least|at most) )?"
        rf"{_TIMES}",
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
        r"(?:an? )?(?P<par>even|odd)[- ]length(?: (?:binary )?(?:strings?|words?|sequences?))?",
        lambda m: _length_parity(m["par"].lower()),
    ),
    (
        rf"(?:of )?(?:a )?length (?:is )?(?:between|from) {_n('low')} (?:and|to) {_n('high')}"
        r"(?: inclusive)?",
        lambda m: _length_between(_number(m["low"]), _number(m["high"])),
    ),
    (
        r"(?:the )?length (?:is )?not (?P<par>even|odd)",
        lambda m: _length_parity("odd" if m["par"].lower() == "even" else "even"),
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
        rf"(?:the )?(?:(?P<k>{lx.ORDINAL})[- ](?:to[- ])?last|(?P<last>last|final)) "
        rf"{lx.SYMBOL_NOUN} "
        rf"(?:is|equals|=) {_s()}",
        lambda m: _kth(_ordinal(m["k"]) if m["k"] else 1, m["s"], True),
    ),
    (
        rf"(?:{lx.HAVE} )?{_s()} as (?:the|its|their) (?:(?P<k>{lx.ORDINAL})|(?P<last>last)) "
        rf"{lx.SYMBOL_NOUN}(?P<end> from the (?:end|right))?",
        lambda m: _kth(
            _ordinal(m["k"]) if m["k"] else 1, m["s"], m["end"] is not None or bool(m["last"])
        ),
    ),
    (
        rf"(?:looks? like )?{_ARTICLE}{_p('x')} followed by "
        rf"(?P<q>any number of|zero or more|one or more) {_s('y')}",
        lambda m: _then_repeated(m["x"], m["y"], m["q"].lower() == "one or more"),
    ),
    (
        rf"(?:every|each) (?:(?P<k>{lx.ORDINAL})|(?P<other>other)) {lx.SYMBOL_NOUN} "
        rf"(?:is|equals|=) {_s()}",
        lambda m: _every_kth(2 if m["other"] else _ordinal(m["k"]), m["s"]),
    ),
    (
        # "any" goes with the leading filler, so "number of" stands alone here.
        r"(?P<q>zero or more|(?:any )?number of|one or more) "
        rf"(?:copies|repetitions|repeats) of {_p()}",
        lambda m: _repetition(m["p"], m["q"].lower() == "one or more"),
    ),
    (
        rf"(?:every|each) {_s('x')} is (?:immediately |directly )?"
        rf"(?P<rel>followed|preceded) by {_ARTICLE}{_s('y')}",
        lambda m: _every_next(m["x"], m["y"], m["rel"].lower() == "preceded"),
    ),
    (
        r"(?:(?:equal to|exactly|in the set|either) )?one of:? (?P<list>.+)",
        lambda m: _words(m["list"]),
    ),
    (
        r"(?:(?:exactly|only|just|precisely) )?(?:the )?(?:(?:words?|strings?|set)\s+)?"
        rf"(?:like |such as )?(?P<list>{_LIST})",
        lambda m: _words(m["list"]),
    ),
    (
        rf"(?:the )?(?:substring |pattern )?{_p()} (?:appears?|occurs?)"
        r"(?: somewhere| as an? (?:substring|subword|factor))?",
        lambda m: _predicate("contains")(m["p"]),
    ),
    (
        rf"{lx.HAVE} {_p()} as an? (?:substring|subword|factor|infix)",
        lambda m: _predicate("contains")(m["p"]),
    ),
    (
        rf"{lx.HAVE} (?:the |an? )?(?:substring |subword |factor |pattern |string )?{_p()}"
        r"(?: (?:somewhere|anywhere)(?: in it)?)?",
        lambda m: _predicate("contains")(m["p"]),
    ),
    (
        rf"(?:(?:is|are|equals?) )?(?:exactly|just|only|precisely) "
        rf"(?:the (?:word|string) )?(?P<list>{_ITEM})",
        lambda m: _words(m["list"]),
    ),
    (
        r"(?:(?:matching|matches|matched by|described by|generated by|given by|of the form"
        r"|the form|form) )?"
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
