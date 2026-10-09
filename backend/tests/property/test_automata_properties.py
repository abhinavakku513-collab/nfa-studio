from itertools import pairwise

from hypothesis import given, reject, settings
from hypothesis import strategies as st

from nfa_studio.core.determinize import complete, determinize, negate, remove_epsilon
from nfa_studio.core.minimize import minimize
from nfa_studio.core.model import EPS
from nfa_studio.core.product import product
from nfa_studio.core.simulate import accepts, simulate
from nfa_studio.ir.limits import StateLimitExceeded
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import Regex
from tests.support.machines import render, thompson
from tests.support.strategies import regex_asts, word_in, words


@given(st.data())
def test_witness_is_an_accepting_path_for_the_word(data: st.DataObject) -> None:
    """CLAUDE.md C1, on random Thompson machines, which are full of ε edges and ε-cycles."""
    ast = data.draw(regex_asts())
    auto = thompson(ast)
    word = data.draw(word_in(ast))
    trace = simulate(auto, word)
    assert trace.accepted
    assert trace.witness is not None
    path = trace.witness
    assert path[0][0] == auto.start
    assert all(left[2] == right[0] for left, right in pairwise(path))
    assert all(r in auto.targets(q, label) for q, label, r in path)
    assert "".join(label for _, label, _ in path if label != EPS) == word
    assert path[-1][2] in auto.final


@given(regex_asts(), words)
def test_simulator_agrees_with_the_oracle(ast: tuple[object, ...], word: str) -> None:
    auto = thompson(ast)
    expected = matches(Regex(expr=render(ast)), word)
    assert simulate(auto, word).accepted == expected
    assert accepts(auto, word) == expected


# The constructions run under their own 2 s budget; Hypothesis's 200 ms deadline would
# only measure how fast this machine is. Hitting the state cap is correct behaviour for
# a large random input, so those examples are skipped rather than counted as failures.
@settings(deadline=None)
@given(regex_asts(max_leaves=5), st.lists(words, max_size=10))
def test_constructions_preserve_the_language(ast: tuple[object, ...], sample: list[str]) -> None:
    auto = thompson(ast)
    free = remove_epsilon(auto)
    try:
        dfa = determinize(auto)
        opposite = negate(auto)
    except StateLimitExceeded:
        reject()
    smallest = minimize(complete(dfa))
    for word in sample:
        expected = accepts(auto, word)
        assert accepts(free, word) == expected
        assert accepts(dfa, word) == expected
        assert accepts(smallest, word) == expected
        assert accepts(opposite, word) != expected
        assert accepts(negate(opposite), word) == expected


@settings(deadline=None)
@given(regex_asts(max_leaves=4), regex_asts(max_leaves=4), st.lists(words, max_size=10))
def test_product_and_de_morgan(
    left: tuple[object, ...], right: tuple[object, ...], sample: list[str]
) -> None:
    a, b = thompson(left), thompson(right)
    try:
        both = product(remove_epsilon(a), remove_epsilon(b))
        # ¬(¬A ∩ ¬B) = A ∪ B
        either = negate(product(negate(a), negate(b)))
    except StateLimitExceeded:
        reject()
    for word in sample:
        in_a, in_b = accepts(a, word), accepts(b, word)
        assert accepts(both, word) == (in_a and in_b)
        assert accepts(either, word) == (in_a or in_b)
