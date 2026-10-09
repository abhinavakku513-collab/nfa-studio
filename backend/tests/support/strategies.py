"""Hypothesis strategies for regex ASTs, words in their languages and random IR trees."""

import random

from hypothesis import strategies as st

from nfa_studio.ir.schema import (
    And,
    Avoids,
    Concat,
    Contains,
    EndsWith,
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
from tests.support.machines import RegexAst, render

words = st.text(alphabet="ab", max_size=8)


def regex_asts(max_leaves: int = 6, alphabet: str = "ab") -> st.SearchStrategy[RegexAst]:
    leaves = st.sampled_from([*(("sym", a) for a in alphabet), ("eps",)])
    return st.recursive(
        leaves,
        lambda kids: st.one_of(
            st.tuples(st.sampled_from(["cat", "alt"]), kids, kids),
            st.tuples(st.sampled_from(["star", "plus", "opt"]), kids),
        ),
        max_leaves=max_leaves,
    )


@st.composite
def word_in(draw: st.DrawFn, ast: RegexAst) -> str:
    """A word of L(ast), drawn by walking the AST."""
    match ast:
        case ("sym", a):
            return str(a)
        case ("eps",):
            return ""
        case ("cat", x, y):
            return draw(word_in(x)) + draw(word_in(y))
        case ("alt", x, y):
            return draw(word_in(draw(st.sampled_from([x, y]))))
        case (op, x):
            low = 1 if op == "plus" else 0
            high = 1 if op == "opt" else 3
            return "".join(draw(word_in(x)) for _ in range(draw(st.integers(low, high))))
    raise ValueError(ast)


def ir_leaves(alphabet: str) -> st.SearchStrategy[Node]:
    patterns = st.text(alphabet=alphabet, min_size=1, max_size=3)
    symbols = st.sampled_from(list(alphabet))
    counts = st.integers(0, 3)
    ops = st.sampled_from(["eq", "ge", "le"])
    return st.one_of(
        st.builds(StartsWith, pattern=patterns),
        st.builds(EndsWith, pattern=patterns),
        st.builds(Contains, pattern=patterns),
        st.builds(Avoids, pattern=patterns),
        st.builds(SymbolCount, symbol=symbols, op=ops, n=counts),
        st.builds(SymbolParity, symbol=symbols, parity=st.sampled_from(["even", "odd"])),
        st.integers(1, 3).flatmap(
            lambda m: st.builds(LengthMod, m=st.just(m), r=st.integers(0, m - 1))
        ),
        st.builds(PatternCount, pattern=patterns, op=ops, n=counts, overlap=st.booleans()),
        st.builds(Regex, expr=regex_asts(max_leaves=4, alphabet=alphabet).map(render)),
        st.builds(
            LiteralSet,
            words=st.lists(st.text(alphabet, max_size=3), min_size=1, max_size=3).map(tuple),
        ),
    )


def ir_trees(alphabet: str = "ab", levels: int = 3) -> st.SearchStrategy[Node]:
    """IR trees over `alphabet` whose longest root-to-leaf path has at most `levels` nodes."""
    if levels == 1:
        return ir_leaves(alphabet)
    kids = ir_trees(alphabet, levels - 1)
    # Combinators first: Hypothesis leans towards earlier branches, and the leaves
    # already get exhaustive unit tests.
    return st.one_of(
        st.builds(And, children=st.lists(kids, min_size=2, max_size=3).map(tuple)),
        st.builds(Or, children=st.lists(kids, min_size=2, max_size=3).map(tuple)),
        st.builds(Concat, children=st.lists(kids, min_size=2, max_size=2).map(tuple)),
        st.builds(Not, child=kids),
        st.builds(Star, child=kids),
        ir_leaves(alphabet),
    )


def shuffled(node: Node, rnd: random.Random) -> Node:
    """`node` with the children of every and/or permuted; the language is unchanged."""
    match node:
        case And(children=children) | Or(children=children):
            kids = [shuffled(child, rnd) for child in children]
            rnd.shuffle(kids)
            return type(node)(children=tuple(kids))
        case Concat(children=children):
            return Concat(children=tuple(shuffled(child, rnd) for child in children))
        case Not(child=child):
            return Not(child=shuffled(child, rnd))
        case Star(child=child):
            return Star(child=shuffled(child, rnd))
    return node
