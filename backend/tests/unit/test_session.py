import pytest

from nfa_studio.api.deps import TokenBucket
from nfa_studio.interpret import interpret
from nfa_studio.session.clarify import (
    Asking,
    EditIR,
    Outcome,
    Ready,
    UnknownAnswer,
    answer,
    open_draft,
)
from nfa_studio.session.store import TTLStore


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def start(text: str) -> Outcome:
    return open_draft(interpret(text), text)


def test_an_answer_is_merged_into_the_partial_ir() -> None:
    asked = start("strings over {a,b} that contain aba twice")
    assert isinstance(asked, Asking)
    done = answer(asked.session, asked.question.id, "no")
    assert isinstance(done, Ready)
    assert done.ir.language.model_dump() == {
        "type": "pattern_count",
        "pattern": "aba",
        "op": "ge",
        "n": 2,
        "overlap": False,
    }
    assert [(c.topic, c.answer) for c in done.ir.clarifications] == [("overlap", "no")]


def test_two_questions_are_asked_one_after_the_other() -> None:
    first = start("strings over {a,b} that contain two a's and contain aba twice")
    assert isinstance(first, Asking)
    assert (first.question.id, first.question.topic) == ("Q1", "count_exact_or_at_least")
    second = answer(first.session, "Q1", "at_least")
    assert isinstance(second, Asking)
    assert (second.question.id, second.question.topic) == ("Q2", "overlap")
    done = answer(second.session, "Q2", "yes")
    assert isinstance(done, Ready)


def test_a_third_question_sends_the_ir_to_the_manual_form() -> None:
    """C13: at most two questions per request, then status edit_ir with the partial IR."""
    result = start(
        "strings over {a,b} that contain two a's and contain aba twice and contain bab twice"
    )
    assert isinstance(result, EditIR)
    assert result.missing == ("count_exact_or_at_least", "overlap", "overlap")
    assert result.partial_ir["language"]["type"] == "and"


def test_a_grouping_answer_can_open_a_nested_question() -> None:
    asked = start("strings over {a,b} that contain two a's and end with b or start with a")
    assert isinstance(asked, Asking) and asked.question.topic == "grouping"
    nested = answer(asked.session, "Q1", "g1")
    assert isinstance(nested, Asking)
    assert (nested.question.id, nested.question.topic) == ("Q2", "count_exact_or_at_least")


def test_edit_manually_returns_the_partial_ir() -> None:
    asked = start("strings that contain two a's")
    assert isinstance(asked, Asking)
    result = answer(asked.session, "Q1", "edit")
    assert isinstance(result, EditIR)
    assert result.partial_ir["language"] == {"type": "symbol_count", "symbol": "a", "n": 2}


def test_answers_must_match_the_pending_question() -> None:
    asked = start("strings that contain two a's")
    assert isinstance(asked, Asking)
    with pytest.raises(UnknownAnswer, match="answer Q1 first"):
        answer(asked.session, "Q2", "exactly")
    with pytest.raises(UnknownAnswer, match="use one of exactly, at_least, edit"):
        answer(asked.session, "Q1", "maybe")


def test_alphabet_dependent_parts_follow_the_alphabet_answer() -> None:
    asked = start("strings over letters whose third symbol from the end is a")
    assert isinstance(asked, Asking) and asked.question.topic == "alphabet"
    done = answer(asked.session, "Q1", "mentioned")
    assert isinstance(done, Ready)
    assert done.ir.alphabet.symbols == ("a", "b")
    widened = start("strings over letters whose third symbol from the end is b")
    assert isinstance(widened, Asking)
    result = answer(widened.session, "Q1", "wider")
    assert isinstance(result, Ready)
    assert result.ir.alphabet.symbols == ("a", "b", "c")
    star = result.ir.language.model_dump(mode="json")["children"][0]
    assert star == {"type": "star", "child": {"type": "literal_set", "words": ["a", "b", "c"]}}


def test_store_entries_expire() -> None:
    clock = Clock()
    store: TTLStore[str, int] = TTLStore(ttl=10, clock=clock)
    store.put("a", 1)
    clock.now = 9.9
    assert store.get("a") == 1
    clock.now = 10
    assert store.get("a") is None
    assert len(store) == 0


def test_store_drops_the_oldest_when_full() -> None:
    store: TTLStore[str, int] = TTLStore(ttl=10, capacity=2, clock=Clock())
    for i, key in enumerate("abc"):
        store.put(key, i)
    assert (store.get("a"), store.get("b"), store.get("c")) == (None, 1, 2)


def test_token_bucket_allows_a_burst_then_refills() -> None:
    clock = Clock()
    bucket = TokenBucket(burst=2, per_second=0.5, clock=clock)
    assert bucket.take("ip") == 0 and bucket.take("ip") == 0
    assert bucket.take("ip") == pytest.approx(2.0)
    assert bucket.take("other") == 0
    clock.now = 2.0
    assert bucket.take("ip") == 0
