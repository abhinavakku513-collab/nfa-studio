"""Hand-built machines and a test-only Thompson builder for random ε-NFAs."""

from collections.abc import Iterable, Mapping
from itertools import count, product
from typing import Any

from nfa_studio.core.model import EPS, EPS_LABEL, Automaton, Kind
from nfa_studio.core.simulate import accepts

RegexAst = tuple[Any, ...]


def machine(
    edges: Iterable[tuple[str, str, str]],
    *,
    final: Iterable[str],
    start: str = "q0",
    alphabet: tuple[str, ...] = ("a", "b"),
    extra_states: Iterable[str] = (),
    kind: Kind = "enfa",
    meanings: Mapping[str, str] | None = None,
) -> Automaton:
    """Build a machine from (src, label, dst) edges; the label "ε" is an ε edge.

    States are numbered in order of first appearance, starting with `start`.
    """
    states = {start: None}
    delta: dict[tuple[str, str], set[str]] = {}
    for q, label, r in edges:
        states.update({q: None, r: None})
        delta.setdefault((q, EPS if label == EPS_LABEL else label), set()).add(r)
    states.update(dict.fromkeys(extra_states))
    states.update(dict.fromkeys(final))
    return Automaton(
        states=tuple(states),
        alphabet=alphabet,
        delta={key: frozenset(dsts) for key, dsts in delta.items()},
        start=start,
        final=frozenset(final),
        meanings=meanings or {},
        kind=kind,
    )


def accepted_words(auto: Automaton, max_len: int = 7) -> set[str]:
    """Every word of length at most `max_len` that `auto` accepts."""
    return {
        word
        for n in range(max_len + 1)
        for word in map("".join, product(auto.alphabet, repeat=n))
        if accepts(auto, word)
    }


# spec §7.5: strings over {a, b} ending with ab.
ENDS_WITH_AB = machine(
    [("q0", "a", "q0"), ("q0", "b", "q0"), ("q0", "a", "q1"), ("q1", "b", "q2")],
    final={"q2"},
    kind="nfa",
    meanings={
        "q0": "scanning (no commitment)",
        "q1": "guessed that an a starts the final ab",
        "q2": "completed ab",
    },
)


def render(ast: RegexAst) -> str:
    """C6 regex text for an AST, fully parenthesised."""
    match ast:
        case ("sym", a):
            return str(a)
        case ("eps",):
            return EPS_LABEL
        case ("cat", x, y):
            return f"({render(x)})({render(y)})"
        case ("alt", x, y):
            return f"({render(x)})|({render(y)})"
        case ("star", x):
            return f"({render(x)})*"
        case ("plus", x):
            return f"({render(x)})+"
        case ("opt", x):
            return f"({render(x)})?"
    raise ValueError(ast)


def thompson(ast: RegexAst, alphabet: tuple[str, ...] = ("a", "b")) -> Automaton:
    """Thompson's construction: one start and one accepting state per fragment.

    Stars of nullable expressions such as (ε)* or (a*)* create ε-cycles.
    """
    ids = count()
    edges: list[tuple[str, str, str]] = []

    def new() -> str:
        return f"t{next(ids)}"

    def build(node: RegexAst) -> tuple[str, str]:
        match node:
            case ("sym", a):
                s, e = new(), new()
                edges.append((s, str(a), e))
            case ("eps",):
                s, e = new(), new()
                edges.append((s, EPS_LABEL, e))
            case ("cat", x, y):
                xs, xe = build(x)
                ys, ye = build(y)
                edges.append((xe, EPS_LABEL, ys))
                s, e = xs, ye
            case ("alt", x, y):
                s = new()
                xs, xe = build(x)
                ys, ye = build(y)
                e = new()
                edges.extend(
                    [(s, EPS_LABEL, xs), (s, EPS_LABEL, ys), (xe, EPS_LABEL, e), (ye, EPS_LABEL, e)]
                )
            case (op, x) if op in ("star", "plus", "opt"):
                s = new()
                xs, xe = build(x)
                e = new()
                edges.extend([(s, EPS_LABEL, xs), (xe, EPS_LABEL, e)])
                if op in ("star", "plus"):
                    edges.append((xe, EPS_LABEL, xs))
                if op in ("star", "opt"):
                    edges.append((s, EPS_LABEL, e))
            case _:
                raise ValueError(node)
        return s, e

    start, end = build(ast)
    return machine(edges, start=start, final={end}, alphabet=alphabet)
