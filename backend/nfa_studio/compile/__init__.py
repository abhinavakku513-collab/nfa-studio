"""IR → the canonical NFA, free of ε-moves, with a construction log (spec §7, C19)."""

from dataclasses import dataclass
from typing import Final, assert_never

from nfa_studio.compile import atoms
from nfa_studio.compile.combine import concat, intersection, star, union
from nfa_studio.compile.naming import name_states
from nfa_studio.compile.regex_parser import RegexSyntaxError, parse_regex
from nfa_studio.compile.thompson import thompson
from nfa_studio.core.determinize import negate, remove_epsilon
from nfa_studio.core.model import Automaton, has_epsilon
from nfa_studio.ir.limits import Budget
from nfa_studio.ir.normalize import IRInvalid, normalize
from nfa_studio.ir.schema import (
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

EMPTY_LANGUAGE_WARNING: Final = (
    "This specification describes the empty language ∅ (no string is accepted)."
)


@dataclass(frozen=True)
class LogEntry:
    """How one IR node (or the final naming pass) was built, and the size it reached."""

    node: str
    text: str
    states: int


@dataclass(frozen=True)
class Compiled:
    automaton: Automaton
    log: tuple[LogEntry, ...]
    warnings: tuple[str, ...]


def compile(doc: IRDocument, budget: Budget | None = None) -> Compiled:
    """Build the named, ε-free NFA for `doc`, logging each node in post-order.

    The document is normalised first, so and/or children in any order give the
    identical machine. All nodes share one budget, and every node's machine is
    checked against max_states, which raises E_STATE_LIMIT. An empty language is
    still returned, with a warning (CLAUDE.md item 9).
    """
    doc = normalize(doc)
    budget = budget or Budget()
    log: list[LogEntry] = []
    built = _compile(doc.language, doc.alphabet.symbols, budget, log)
    # CLAUDE.md C19: the machine shown, simulated and verified has no ε-moves, whatever
    # the constructions above used to join their parts.
    if has_epsilon(built):
        built = remove_epsilon(built)
        log.append(
            LogEntry(
                "epsilon_removal",
                "ε-removal: each state gets, for every symbol, the states its ε-closure "
                "reaches on that symbol, followed by their ε-closures, and accepts if its "
                "ε-closure holds an accepting state. States entered only by ε moves are "
                "then unreachable and dropped. The result is an NFA with no ε moves.",
                len(built.states),
            )
        )
    auto = name_states(built)
    n = len(auto.states)
    naming = (
        f"States were renamed q0 … q{n - 1} breadth-first from the start state, "
        "taking symbols in alphabet order and ε last."
    )
    if auto.dead:
        naming += (
            f" {len(auto.dead)} state{'s' if len(auto.dead) > 1 else ''} cannot reach an "
            "accepting state; they stay in the model and are hidden by default."
        )
    log.append(LogEntry("naming", naming, n))
    warnings = () if auto.final else (EMPTY_LANGUAGE_WARNING,)
    return Compiled(auto, tuple(log), warnings)


def _compile(
    node: Node, alphabet: tuple[str, ...], budget: Budget, log: list[LogEntry]
) -> Automaton:
    auto, text = _build(node, alphabet, budget, log)
    budget.check(len(auto.states))
    log.append(LogEntry(node.type, text, len(auto.states)))
    return auto


def _build(
    node: Node, alphabet: tuple[str, ...], budget: Budget, log: list[LogEntry]
) -> tuple[Automaton, str]:
    def parts(children: tuple[Node, ...]) -> list[Automaton]:
        return [_compile(child, alphabet, budget, log) for child in children]

    match node:
        case StartsWith(pattern=p):
            return atoms.starts_with(p, alphabet), (
                f"starts_with {p}: a chain that reads {p}; a mismatch has no edge, so that "
                "branch dies, and the last state loops on every symbol."
            )
        case EndsWith(pattern=p):
            return atoms.ends_with(p, alphabet), (
                f"ends_with {p}: the start state loops on every symbol and on each {p[0]} also "
                f"guesses that the final {p} begins there; the last state has no outgoing "
                "edge, so a match must end the input."
            )
        case Contains(pattern=p):
            return atoms.contains(p, alphabet), (
                f"contains {p}: like ends_with, but the last state loops on every symbol, so "
                f"the rest of the input is free once {p} has been found."
            )
        case Avoids(pattern=p):
            return atoms.avoids(p, alphabet), (
                f"avoids {p}: a DFA that tracks how much of {p} the input currently ends with "
                f"(KMP); completing {p} leads to an explicit dead state. It is built directly, "
                "without subset construction."
            )
        case SymbolCount(symbol=s, op=op, n=n):
            rest = {
                "eq": f"a further {s} has no edge, and the counter at {n} accepts",
                "ge": f"the counter at {n} loops on every symbol and accepts",
                "le": f"a further {s} has no edge, and every counter accepts",
            }[op]
            return atoms.symbol_count(s, op, n, alphabet), (
                f"symbol_count {s} {op} {n}: one state per number of {s} seen, up to {n}; {rest}."
            )
        case SymbolParity(symbol=s, parity=parity):
            return atoms.symbol_parity(s, parity == "even", alphabet), (
                f"symbol_parity {s} {parity}: two states that swap on each {s}; zero counts "
                "as even."
            )
        case LengthMod(m=m, r=r):
            return atoms.length_mod(m, r, alphabet), (
                f"length_mod {m} {r}: a cycle of {m} states, one per remainder of the length; "
                f"the state for remainder {r} accepts."
            )
        case LiteralSet(words=words):
            listed = ", ".join(w or "ε" for w in words)
            return atoms.literal_set(words, alphabet), (
                f"literal_set {{{listed}}}: a trie whose states are the prefixes read so far; "
                "the ends of the listed words accept."
            )
        case PatternCount(pattern=p, op=op, n=n, overlap=overlap):
            resume = (
                "at its longest border, so occurrences may overlap"
                if overlap
                else "from scratch, so occurrences are disjoint"
            )
            return atoms.pattern_count(p, op, n, overlap, alphabet), (
                f"pattern_count {p} {op} {n}: the KMP DFA of {p} paired with an occurrence "
                f"counter; after a match the search resumes {resume}."
            )
        case Regex(expr=expr):
            try:
                tree = parse_regex(expr)
            except RegexSyntaxError as exc:
                raise IRInvalid([str(exc)]) from exc
            return thompson(tree, alphabet), (
                f"regex {expr}: Thompson's construction; ε edges join the fragments for "
                "concatenation, union and repetition."
            )
        case And(children=children):
            return intersection(parts(children), budget), (
                f"and: ε-removal on each of the {len(children)} parts, then the product "
                "construction; a pair of states accepts when both accept."
            )
        case Or(children=children):
            return union(parts(children)), (
                f"or: a new start state with ε edges into each of the {len(children)} alternatives."
            )
        case Not(child=child):
            return negate(_compile(child, alphabet, budget, log), budget), (
                "not: ε-removal, subset construction, completion with a dead state, then "
                "swapping accepting and non-accepting states. The result is a DFA produced by "
                "complement, not a hand-built NFA."
            )
        case Concat(children=children):
            return concat(parts(children)), (
                f"concat: ε edges from the accepting states of each of the {len(children)} "
                "parts to the start of the next."
            )
        case Star(child=child):
            return star(_compile(child, alphabet, budget, log)), (
                "star: a new accepting start state with an ε edge into the body and ε edges "
                "back from the body's accepting states, so ε is accepted."
            )
        case _:
            assert_never(node)
