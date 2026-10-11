"""The AI tier through the API, with a mock model: read, refuse, verify, limit (C18)."""

import pytest
from fastapi.testclient import TestClient

from nfa_studio.api.app import app
from nfa_studio.api.deps import TokenBucket, get_llm, get_llm_limiter
from nfa_studio.interpret import llm_adapter
from nfa_studio.verify.ladder import VerificationFailed
from tests.support.api import Clock, error
from tests.support.mock_llm import MockModel, not_regular, reading

UNREADABLE = "a string over {a,b} is accepted iff it holds the pair ab"
AB = reading({"type": "contains", "pattern": "ab"}, "ab", "user")


def use(model: MockModel) -> MockModel:
    tier = model.tier()
    app.dependency_overrides[get_llm] = lambda: tier
    return model


def test_a_reading_with_ai_help_is_marked_and_still_confirmed(client: TestClient) -> None:
    model = use(MockModel({UNREADABLE: AB}))
    body = client.post("/v1/interpret", json={"text": UNREADABLE}).json()
    assert body["status"] == "ready"
    assert body["ir"]["language"] == {"type": "contains", "pattern": "ab"}
    assert body["ir"]["assumptions"][0]["id"] == "llm_interpreted"
    assert model.calls == [UNREADABLE]
    # Building it goes through the same ladder as any other specification.
    built = client.post("/v1/automata", json=body["ir"]).json()
    assert built["verification"]["badge"] == "green"


def test_what_the_rules_read_never_reaches_the_model(client: TestClient) -> None:
    model = use(MockModel())
    assert client.post("/v1/interpret", json={"text": "binary strings ending in 01"}).is_success
    assert model.calls == []


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("strings whose a's and b's come in equal numbers", "equal_counts"),
        ("strings that read the same forwards and backwards", "palindrome"),
        ("words whose length is one of 2, 3, 5, 7, 11 and so on", "length_not_periodic"),
        ("properly nested pairs of ( and )", "balanced_brackets"),
        ("a's then the same amount of b's", "power_counting"),
    ],
)
def test_the_model_refuses_non_regular_languages_like_the_rules(
    client: TestClient, text: str, kind: str
) -> None:
    use(MockModel({text: not_regular(kind)}))
    body = error(client.post("/v1/interpret", json={"text": text}), 422, "E_UNSUPPORTED_NONREGULAR")
    assert body["detail"]["reason"] == kind
    assert body["detail"]["alternative"]["text"].startswith("Try")


def test_an_unknown_non_regular_family_still_gets_an_alternative(client: TestClient) -> None:
    use(MockModel({UNREADABLE: not_regular("something new")}))
    body = error(
        client.post("/v1/interpret", json={"text": UNREADABLE}), 422, "E_UNSUPPORTED_NONREGULAR"
    )
    assert body["detail"]["reason"] == "not_regular"
    assert body["detail"]["alternative"]["text"].startswith("Try a bounded version")


def test_a_reading_that_cannot_be_verified_ends_in_the_refusal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(*_: object) -> None:
        raise VerificationFailed("V1", "ab", "the automaton rejects 'ab'")

    monkeypatch.setattr(llm_adapter, "verify", failing)
    use(MockModel({UNREADABLE: AB}))
    body = error(
        client.post("/v1/interpret", json={"text": UNREADABLE}), 422, "E_UNSUPPORTED_FEATURE"
    )
    assert "could not be built and verified" in body["message"]


def test_a_reading_too_large_to_build_ends_in_the_refusal(client: TestClient) -> None:
    star = {"type": "star", "child": {"type": "literal_set", "words": ["a", "b"]}}
    huge = {
        "type": "and",
        "children": [{"type": "contains", "pattern": "a" * 16}]
        + [{"type": "symbol_count", "symbol": s, "op": "eq", "n": 20} for s in "ab"]
        + [{"type": "concat", "children": [star, {"type": "literal_set", "words": ["b" * 16]}]}],
    }
    use(MockModel({UNREADABLE: reading(huge, "ab", "user")}))
    body = error(
        client.post("/v1/interpret", json={"text": UNREADABLE}), 422, "E_UNSUPPORTED_FEATURE"
    )
    assert "could not be built and verified" in body["message"]


def test_model_calls_have_their_own_per_address_limit(client: TestClient, clock: Clock) -> None:
    bucket = TokenBucket(burst=2, per_second=0.5, clock=clock)
    app.dependency_overrides[get_llm_limiter] = lambda: bucket
    texts = [f"{UNREADABLE} number {i}" for i in range(3)]
    use(MockModel({text: AB for text in texts}))
    for text in texts[:2]:
        assert client.post("/v1/interpret", json={"text": text}).json()["status"] == "ready"
    response = client.post("/v1/interpret", json={"text": texts[2]})
    body = error(response, 429, "E_RATE_LIMITED")
    assert response.headers["retry-after"] == "2"
    assert "with AI help" in body["message"]
    # A reading already made is served from the cache without spending the limit,
    # and the rules are never limited by it.
    assert client.post("/v1/interpret", json={"text": texts[0]}).json()["status"] == "ready"
    assert client.post("/v1/interpret", json={"text": "binary strings ending in 01"}).is_success


def test_descriptions_are_capped_before_any_model_call(client: TestClient) -> None:
    model = use(MockModel())
    error(client.post("/v1/interpret", json={"text": "a" * 501}), 413, "E_INPUT_TOO_LONG")
    assert model.calls == []
