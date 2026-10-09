import random

from hypothesis import given, reject
from hypothesis import strategies as st

from nfa_studio.ir.normalize import IRInvalid, normalize, spec_hash
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import Alphabet, IRDocument, Node
from tests.support.strategies import ir_trees, shuffled


def document(language: Node, symbols: tuple[str, ...] = ("a", "b")) -> IRDocument:
    return IRDocument(alphabet=Alphabet(symbols=symbols, source="user"), language=language)


def normalized(language: Node, symbols: tuple[str, ...] = ("a", "b")) -> IRDocument:
    try:
        return normalize(document(language, symbols))
    except IRInvalid:
        reject()


@given(ir_trees(levels=4), st.randoms(use_true_random=False))
def test_normalisation_is_idempotent_and_order_insensitive(tree: Node, rnd: random.Random) -> None:
    once = normalized(tree)
    assert normalize(once) == once
    permuted = normalized(shuffled(tree, rnd), ("b", "a", "b"))
    assert permuted.language == once.language
    assert spec_hash(permuted) == spec_hash(once)


@given(ir_trees(), st.lists(st.text("ab", max_size=6), max_size=5))
def test_normalisation_preserves_the_language(tree: Node, sample: list[str]) -> None:
    once = normalized(tree)
    for word in sample:
        assert matches(once.language, word) == matches(tree, word)
