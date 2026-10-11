"""GET /branches and POST /branches/simulate: lanes over the same IR, the build untouched."""

from typing import Any

from fastapi.testclient import TestClient

from tests.support.api import build, error

CONTAINS_101_AND_ENDS_00 = {
    "type": "and",
    "children": [
        {"type": "contains", "pattern": "101"},
        {"type": "ends_with", "pattern": "00"},
    ],
}


def run(client: TestClient, automaton_id: str, word: str, page: int = 1) -> Any:
    response = client.post(
        f"/v1/automata/{automaton_id}/branches/simulate", json={"word": word, "page": page}
    )
    assert response.status_code == 200, response.json()
    return response.json()


def test_lanes_come_with_label_drawing_and_graph(client: TestClient) -> None:
    automaton_id = build(client, CONTAINS_101_AND_ENDS_00, "01")
    before = client.get(f"/v1/automata/{automaton_id}").json()

    body = client.get(f"/v1/automata/{automaton_id}/branches").json()
    assert (body["automaton_id"], body["combiner"]) == (automaton_id, "all")
    assert [b["label"] for b in body["branches"]] == ["contain 101", "end with 00"]
    for index, lane in enumerate(body["branches"]):
        assert lane["index"] == index
        assert lane["graph"]["model_hash"] == lane["automaton_id"]
        assert lane["svg"].lstrip().startswith(("<?xml", "<svg", "<!DOCTYPE"))
        assert 'id="s-q0"' in lane["svg"]
        assert lane["state_count"] == len(lane["graph"]["nodes"]) + len(
            lane["graph"]["hidden_dead_states"]
        )

    # The verified automaton and its report are what they were.
    assert client.get(f"/v1/automata/{automaton_id}").json() == before


def test_or_and_not(client: TestClient) -> None:
    either = build(
        client,
        {"type": "or", "children": CONTAINS_101_AND_ENDS_00["children"]},
        "01",
    )
    assert client.get(f"/v1/automata/{either}/branches").json()["combiner"] == "any"

    but_not = build(
        client,
        {
            "type": "and",
            "children": [
                {"type": "contains", "pattern": "101"},
                {"type": "not", "child": {"type": "ends_with", "pattern": "00"}},
            ],
        },
        "01",
    )
    lanes = client.get(f"/v1/automata/{but_not}/branches").json()["branches"]
    assert [(b["label"], b["negated"], b["kind"]) for b in lanes] == [
        ("contain 101", False, "nfa"),
        ("NOT end with 00", True, "dfa"),
    ]


def test_a_single_condition_has_an_empty_list(client: TestClient) -> None:
    automaton_id = build(client, {"type": "ends_with", "pattern": "01"}, "01")
    body = client.get(f"/v1/automata/{automaton_id}/branches").json()
    assert (body["combiner"], body["branches"]) == (None, [])
    trace = run(client, automaton_id, "01")
    assert (trace["steps"], trace["combined"], trace["total_steps"]) == ([], None, 0)


def test_one_word_on_every_lane(client: TestClient) -> None:
    automaton_id = build(client, CONTAINS_101_AND_ENDS_00, "01")
    for word, lanes, combined in [
        ("10100", [True, True], True),
        ("101", [True, False], False),
        ("10101", [True, False], False),
    ]:
        body = run(client, automaton_id, word)
        assert (body["accepted"], body["combined"]) == (lanes, combined)
        main = client.post(f"/v1/automata/{automaton_id}/simulate", json={"word": word}).json()
        assert body["combined"] == main["accepted"]
        assert body["total_steps"] == len(word) + 1
        step = body["steps"][-1]
        assert (step["accepting"], step["combined"]) == (lanes, combined)
        assert all(len(s["active"]) == 2 for s in body["steps"])


def test_long_traces_are_paged_like_simulate(client: TestClient) -> None:
    automaton_id = build(client, CONTAINS_101_AND_ENDS_00, "01")
    word = "10" * 250
    first = run(client, automaton_id, word)
    assert (first["pages"], len(first["steps"]), first["total_steps"]) == (3, 200, 501)
    third = run(client, automaton_id, word, page=3)
    assert (third["steps"][0]["index"], len(third["steps"])) == (400, 101)
    error(
        client.post(
            f"/v1/automata/{automaton_id}/branches/simulate", json={"word": word, "page": 4}
        ),
        422,
        "E_SCHEMA_INVALID",
    )


def test_unknown_automaton_and_bad_symbol(client: TestClient) -> None:
    error(client.get("/v1/automata/sha256:missing/branches"), 404, "E_AUTOMATON_NOT_FOUND")
    automaton_id = build(client, CONTAINS_101_AND_ENDS_00, "01")
    error(
        client.post(f"/v1/automata/{automaton_id}/branches/simulate", json={"word": "102"}),
        422,
        "E_SYMBOL_NOT_IN_ALPHABET",
    )
