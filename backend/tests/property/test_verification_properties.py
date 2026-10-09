from hypothesis import given, reject, settings
from hypothesis import strategies as st

from nfa_studio.compile import compile
from nfa_studio.core.simulate import accepts
from nfa_studio.ir.limits import StateLimitExceeded, TimeBudgetExceeded
from nfa_studio.ir.normalize import IRInvalid, normalize
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import Alphabet, IRDocument, Node
from nfa_studio.reference.to_dfa import NotTranslatable, reference_dfa
from nfa_studio.verify.ladder import verify
from tests.property.test_compile_properties import alphabets, every_short_word
from tests.support.strategies import ir_trees


def document(tree: Node, symbols: str) -> IRDocument:
    doc = IRDocument(alphabet=Alphabet(symbols=tuple(symbols), source="user"), language=tree)
    try:
        return normalize(doc)
    except IRInvalid:
        reject()


# Each example explores or verifies a whole machine under its own budgets; Hypothesis's
# 200 ms deadline would only measure how fast this machine is.
@settings(deadline=None)
@given(st.data())
def test_reference_agrees_with_the_oracle(data: st.DataObject) -> None:
    """The two independent semantics, derivatives and direct evaluation, agree."""
    symbols = data.draw(alphabets)
    spec = document(data.draw(ir_trees(symbols, levels=3)), symbols)
    try:
        reference = reference_dfa(spec)
    except (NotTranslatable, StateLimitExceeded, TimeBudgetExceeded):
        reject()
    for word in every_short_word(symbols):
        assert accepts(reference, word) == matches(spec.language, word), word


@settings(deadline=None)
@given(ir_trees("ab", levels=3))
def test_every_compiled_specification_passes_the_ladder(tree: Node) -> None:
    spec = document(tree, "ab")
    try:
        auto = compile(spec).automaton
    except StateLimitExceeded:
        reject()
    report = verify(auto, spec)
    assert report.level in ("V1", "V2")
