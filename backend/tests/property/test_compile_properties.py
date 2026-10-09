import random
from itertools import product

from hypothesis import given, reject, settings
from hypothesis import strategies as st

from nfa_studio.compile import Compiled, compile
from nfa_studio.core.model import model_hash
from nfa_studio.core.simulate import simulate
from nfa_studio.ir.limits import StateLimitExceeded
from nfa_studio.ir.normalize import IRInvalid
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import Alphabet, IRDocument, Node
from tests.support.strategies import ir_leaves, ir_trees, shuffled

alphabets = st.sampled_from(["ab", "abc"])


def every_short_word(symbols: str) -> list[str]:
    """Every word up to length 6 over two symbols or 4 over three, where boundary cases
    such as aa or ababa live."""
    longest = 6 if len(symbols) == 2 else 4
    return ["".join(w) for n in range(longest + 1) for w in product(symbols, repeat=n)]


def compiled(language: Node, symbols: str) -> Compiled:
    doc = IRDocument(alphabet=Alphabet(symbols=tuple(symbols), source="user"), language=language)
    try:
        return compile(doc)
    except (StateLimitExceeded, IRInvalid):
        # Both are correct refusals for some random trees (too big, or over 40 nodes).
        reject()


# Compilation runs under its own 2 s budget; Hypothesis's 200 ms deadline would only
# measure how fast this machine is.
@settings(deadline=None)
@given(st.data())
def test_compiled_machine_agrees_with_the_oracle(data: st.DataObject) -> None:
    """simulate(compile(ir)) == oracle(ir) on random IR trees of depth ≤ 3."""
    symbols = data.draw(alphabets)
    tree = data.draw(ir_trees(symbols, levels=3))
    auto = compiled(tree, symbols).automaton
    longer = data.draw(st.lists(st.text(symbols, min_size=7, max_size=10), max_size=8))
    for word in every_short_word(symbols) + longer:
        assert simulate(auto, word).accepted == matches(tree, word), word


@settings(deadline=None)
@given(st.data())
def test_every_atom_agrees_with_the_oracle(data: st.DataObject) -> None:
    """Atoms on their own, where a sibling in a tree cannot mask a wrong answer."""
    symbols = data.draw(alphabets)
    leaf = data.draw(ir_leaves(symbols))
    auto = compiled(leaf, symbols).automaton
    for word in every_short_word(symbols):
        assert simulate(auto, word).accepted == matches(leaf, word), word


@settings(deadline=None)
@given(st.data(), st.randoms(use_true_random=False))
def test_child_order_does_not_change_the_machine(data: st.DataObject, rnd: random.Random) -> None:
    symbols = data.draw(alphabets)
    tree = data.draw(ir_trees(symbols, levels=3))
    first = compiled(tree, symbols).automaton
    again = compiled(shuffled(tree, rnd), symbols[::-1]).automaton
    assert model_hash(again) == model_hash(first)
