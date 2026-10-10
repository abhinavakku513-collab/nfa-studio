"""Limits enforced at the API boundary (spec §5.3, §9.3, §13) and the wording of every
error the API can return (spec §12.2: the reason, then the next action)."""

import re
import subprocess
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nfa_studio.api import deps, routes
from nfa_studio.api.app import app
from nfa_studio.api.deps import TokenBucket, get_client_ip_header, get_limiter
from nfa_studio.api.errors import STATUS
from nfa_studio.compile import Compiled
from nfa_studio.ir.limits import LIMITS, TimeBudgetExceeded
from nfa_studio.render import svg
from tests.support.api import Clock, build, error, ir

CONTAINS_A = {"type": "contains", "pattern": "a"}


def test_a_description_of_exactly_the_limit_is_read(client: TestClient) -> None:
    text = "binary strings ending in 01"
    text += " " * (LIMITS.max_text_len - len(text))
    assert len(text) == LIMITS.max_text_len
    assert client.post("/v1/interpret", json={"text": text}).json()["status"] == "ready"
    body = error(client.post("/v1/interpret", json={"text": text + "1"}), 413, "E_INPUT_TOO_LONG")
    assert body["detail"] == {"length": 501, "limit": 500}


def test_a_word_of_exactly_10000_symbols_is_simulated_in_pages(client: TestClient) -> None:
    automaton_id = build(client, CONTAINS_A)
    word = "ab" * (LIMITS.max_word_len // 2)
    url = f"/v1/automata/{automaton_id}/simulate"
    first = client.post(url, json={"word": word})
    assert first.status_code == 200
    trace = first.json()
    assert (trace["accepted"], trace["total_steps"]) == (True, 10_001)
    assert (trace["pages"], len(trace["steps"])) == (51, 200)
    last = client.post(url, json={"word": word, "page": 51, "witness": False}).json()
    assert [step["index"] for step in last["steps"]] == [10_000]
    assert last["steps"][0]["final_accepted"] is True

    body = error(client.post(url, json={"word": word + "a"}), 413, "E_INPUT_TOO_LONG")
    assert body["detail"] == {"length": 10_001, "limit": 10_000}


def test_a_batch_of_exactly_100_words_is_run(client: TestClient) -> None:
    automaton_id = build(client, CONTAINS_A)
    url = f"/v1/automata/{automaton_id}/simulate/batch"
    words = ["a" * n for n in range(LIMITS.max_batch_size)]
    results = client.post(url, json={"words": words}).json()["results"]
    assert len(results) == 100
    assert [r["accepted"] for r in results] == [False] + [True] * 99

    body = error(client.post(url, json={"words": [*words, "b"]}), 413, "E_INPUT_TOO_LONG")
    assert body["detail"] == {"length": 101, "limit": 100}


@pytest.mark.parametrize(
    ("at_limit", "over_limit", "message"),
    [
        (
            ir({"type": "contains", "pattern": "a" * 16}),
            ir({"type": "contains", "pattern": "a" * 17}),
            "16",
        ),
        (
            ir({"type": "symbol_count", "symbol": "a", "op": "le", "n": 20}),
            ir({"type": "symbol_count", "symbol": "a", "op": "le", "n": 21}),
            "20",
        ),
        # Nested parentheses reach the length limit while the machine stays tiny.
        (
            ir({"type": "regex", "expr": "(" * 99 + "a" + ")" * 99 + "*"}),
            ir({"type": "regex", "expr": "(" * 100 + "a" + ")" * 100}),
            "200",
        ),
        (
            ir(CONTAINS_A, symbols="abcdef"),
            ir(CONTAINS_A, symbols="abcdefg"),
            "6",
        ),
        (
            ir({"type": "or", "children": [CONTAINS_A] * 39}),
            ir({"type": "or", "children": [CONTAINS_A] * 40}),
            "40",
        ),
    ],
    ids=["pattern length", "count", "regex length", "alphabet size", "IR nodes"],
)
def test_ir_size_limits(
    client: TestClient, at_limit: dict[str, Any], over_limit: dict[str, Any], message: str
) -> None:
    assert client.post("/v1/automata", json=at_limit).status_code == 200
    body = error(client.post("/v1/automata", json=over_limit), 422, "E_SCHEMA_INVALID")
    assert any(message in reason for reason in body["detail"]["errors"]), body


def test_the_configured_rate_limit_per_address(client: TestClient, clock: Clock) -> None:
    assert (deps.limiter.burst, deps.limiter.per_second) == (60, 1.0)
    bucket = TokenBucket(LIMITS.rate_limit_burst, LIMITS.rate_limit_per_second, clock=clock)
    app.dependency_overrides[get_limiter] = lambda: bucket
    # /v1/health and /v1/capabilities are public; every other route is limited.
    automaton = f"/v1/automata/{build(client, CONTAINS_A)}"
    assert all(client.get(automaton).status_code == 200 for _ in range(59))
    body = error(client.get(automaton), 429, "E_RATE_LIMITED")
    assert body["detail"] == {"retry_after": 1}

    other = TestClient(app, client=("203.0.113.7", 50000))
    assert other.get(automaton).status_code == 200
    assert client.get("/v1/health").status_code == 200
    clock.now += 1
    assert client.get(automaton).status_code == 200
    assert client.get(automaton).status_code == 429


def test_behind_a_proxy_the_edge_header_names_the_visitor(client: TestClient, clock: Clock) -> None:
    bucket = TokenBucket(2, 1.0, clock=clock)
    app.dependency_overrides[get_limiter] = lambda: bucket
    app.dependency_overrides[get_client_ip_header] = lambda: "CF-Connecting-IP"
    url = "/v1/automata/sha256:0000"
    visitor = {"CF-Connecting-IP": "198.51.100.7"}
    assert [client.get(url, headers=visitor).status_code for _ in range(2)] == [404, 404]
    # Forging X-Forwarded-For buys nothing: the edge header still names this visitor.
    forged = {**visitor, "X-Forwarded-For": "203.0.113.9, 192.0.2.1"}
    error(client.get(url, headers=forged), 429, "E_RATE_LIMITED")
    assert client.get(url, headers={"CF-Connecting-IP": "198.51.100.8"}).status_code == 404
    # A value that is not an address is ignored in favour of the TCP peer.
    assert client.get(url, headers={"CF-Connecting-IP": "not an ip"}).status_code == 404


def test_without_a_proxy_no_header_can_change_the_address(client: TestClient, clock: Clock) -> None:
    bucket = TokenBucket(1, 1.0, clock=clock)
    app.dependency_overrides[get_limiter] = lambda: bucket
    url = "/v1/automata/sha256:0000"
    assert client.get(url).status_code == 404
    for spoof in ({"CF-Connecting-IP": "198.51.100.9"}, {"X-Forwarded-For": "198.51.100.9"}):
        error(client.get(url, headers=spoof), 429, "E_RATE_LIMITED")


# spec §12.2: a message states the reason, then a clause that tells the user what to do.
ACTIONS = frozenset(
    {
        "add",
        "answer",
        "ask",
        "build",
        "correct",
        "describe",
        "install",
        "rephrase",
        "send",
        "shorten",
        "simplify",
        "split",
        "try",
        "use",
        "wait",
    }
)


def reason_then_action(message: str) -> bool:
    clauses = [c.strip() for c in re.split(r"[.;:](?:\s+|$)", message) if c.strip()]
    first_words = [clause.split()[0].lower() for clause in clauses]
    return any(word in ACTIONS for word in first_words[1:])


def _regex_error(client: TestClient) -> Any:
    return client.post("/v1/automata", json=ir({"type": "regex", "expr": "(ab"}))


def _missing_field(client: TestClient) -> Any:
    automaton_id = build(client, CONTAINS_A)
    return client.post(f"/v1/automata/{automaton_id}/simulate", json={})


def _no_such_page(client: TestClient) -> Any:
    automaton_id = build(client, CONTAINS_A)
    return client.post(f"/v1/automata/{automaton_id}/simulate", json={"word": "a", "page": 3})


def _unknown_option(client: TestClient) -> Any:
    asked = client.post("/v1/interpret", json={"text": "strings that contain two a's"}).json()
    return client.post(
        f"/v1/interpret/{asked['session_id']}/answer",
        json={"question_id": "Q1", "option_id": "maybe"},
    )


def _wrong_question(client: TestClient) -> Any:
    asked = client.post("/v1/interpret", json={"text": "strings that contain two a's"}).json()
    return client.post(
        f"/v1/interpret/{asked['session_id']}/answer",
        json={"question_id": "Q2", "option_id": "exactly"},
    )


def _state_limit(client: TestClient) -> Any:
    spec = {
        "type": "and",
        "children": [
            {"type": "length_mod", "m": 14, "r": 0},
            {"type": "length_mod", "m": 15, "r": 0},
        ],
    }
    return client.post("/v1/automata", json=ir(spec))


def _construction_timeout(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    def slow(doc: Any) -> Compiled:
        raise TimeBudgetExceeded(LIMITS.time_budget_seconds)

    monkeypatch.setattr(routes, "compile", slow)
    return client.post("/v1/automata", json=ir(CONTAINS_A))


def _dot_with(failure: BaseException) -> Callable[[TestClient, pytest.MonkeyPatch], Any]:
    def request(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Any:
        automaton_id = build(client, {"type": "ends_with", "pattern": "ba"})

        def run(*args: object, **kwargs: object) -> None:
            raise failure

        svg.run_dot.cache_clear()
        monkeypatch.setattr(svg.subprocess, "run", run)
        return TestClient(app, raise_server_exceptions=False).get(
            f"/v1/automata/{automaton_id}/diagram"
        )

    return request


def _verification_failure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    real = routes.compile

    def wrong(doc: Any) -> Compiled:
        update = {"language": doc.language.model_copy(update={"pattern": "b"})}
        return real(doc.model_copy(update=update))

    monkeypatch.setattr(routes, "compile", wrong)
    return client.post("/v1/automata", json=ir(CONTAINS_A))


def _internal(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    automaton_id = build(client, CONTAINS_A)

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "build_table", broken)
    return TestClient(app, raise_server_exceptions=False).get(f"/v1/automata/{automaton_id}/table")


def _rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    app.dependency_overrides[get_limiter] = lambda: TokenBucket(0, 1.0)
    return client.get("/v1/automata/sha256:0000")


def _expired_session(client: TestClient) -> Any:
    return client.post(
        "/v1/interpret/s_missing/answer", json={"question_id": "Q1", "option_id": "yes"}
    )


Trigger = Callable[..., Any]


def _interpret(text: str) -> Trigger:
    return lambda c: c.post("/v1/interpret", json={"text": text})


# One request for every way the API can fail, grouped by error code.
CASES: list[tuple[str, str, Trigger]] = [
    ("E_SCHEMA_INVALID", "IR field", lambda c: c.post("/v1/automata", json=ir({"type": "x"}))),
    ("E_SCHEMA_INVALID", "regex syntax", _regex_error),
    ("E_SCHEMA_INVALID", "request body", _missing_field),
    ("E_SCHEMA_INVALID", "trace page", _no_such_page),
    ("E_SCHEMA_INVALID", "unknown option", _unknown_option),
    ("E_SCHEMA_INVALID", "wrong question", _wrong_question),
    (
        "E_ALPHABET_MISSING",
        "no symbols",
        lambda c: c.post("/v1/interpret", json={"text": "strings of even length"}),
    ),
    *[
        ("E_UNSUPPORTED_NONREGULAR", text, _interpret(text))
        for text in (
            "a^n b^n",
            "same number of a's and b's",
            "more a's than b's",
            "palindromes over {0,1}",
            "strings whose length is prime over {a}",
            "balanced brackets over {(,)}",
        )
    ],
    (
        "E_UNSUPPORTED_FEATURE",
        "not interpretable",
        lambda c: c.post("/v1/interpret", json={"text": "strings that are good"}),
    ),
    (
        "E_UNSUPPORTED_FEATURE",
        "numeric value",
        lambda c: c.post("/v1/interpret", json={"text": "binary numbers divisible by 3"}),
    ),
    (
        "E_SYMBOL_NOT_IN_ALPHABET",
        "word",
        lambda c: c.post(f"/v1/automata/{build(c, CONTAINS_A)}/simulate", json={"word": "abca"}),
    ),
    (
        "E_INPUT_TOO_LONG",
        "description",
        lambda c: c.post("/v1/interpret", json={"text": "a" * 501}),
    ),
    (
        "E_INPUT_TOO_LONG",
        "word",
        lambda c: c.post(
            f"/v1/automata/{build(c, CONTAINS_A)}/simulate", json={"word": "a" * 10_001}
        ),
    ),
    (
        "E_INPUT_TOO_LONG",
        "batch",
        lambda c: c.post(
            f"/v1/automata/{build(c, CONTAINS_A)}/simulate/batch", json={"words": ["a"] * 101}
        ),
    ),
    ("E_STATE_LIMIT", "construction", _state_limit),
    ("E_TIMEOUT", "construction", _construction_timeout),
    ("E_TIMEOUT", "layout", _dot_with(subprocess.TimeoutExpired("dot", 10))),
    ("E_VERIFY_FAILED", "wrong machine", _verification_failure),
    (
        "E_AUTOMATON_NOT_FOUND",
        "unknown id",
        lambda c: c.get("/v1/automata/sha256:0000"),
    ),
    ("E_RATE_LIMITED", "burst spent", _rate_limited),
    ("E_SESSION_NOT_FOUND", "unknown session", _expired_session),
    ("E_INTERNAL", "unexpected", _internal),
    ("E_INTERNAL", "no graphviz", _dot_with(FileNotFoundError("dot"))),
]


def test_the_audit_covers_every_error_code() -> None:
    # E_NEEDS_CLARIFICATION is a successful answer that carries a question, not an error.
    assert {code for code, _, _ in CASES} == set(STATUS) - {"E_NEEDS_CLARIFICATION"}


@pytest.mark.parametrize(
    ("code", "trigger"),
    [(code, trigger) for code, _, trigger in CASES],
    ids=[f"{code}: {case}" for code, case, _ in CASES],
)
def test_every_error_names_the_reason_and_the_next_action(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, code: str, trigger: Trigger
) -> None:
    takes_patch = trigger.__code__.co_argcount == 2
    response = trigger(client, monkeypatch) if takes_patch else trigger(client)
    body = error(response, STATUS[code], code)
    assert reason_then_action(body["message"]), body["message"]


@pytest.mark.parametrize(
    "message",
    [
        "Something went wrong.",
        "Use a shorter word.",
        "The input is too long",
    ],
)
def test_the_audit_rejects_messages_without_reason_or_action(message: str) -> None:
    assert not reason_then_action(message)
