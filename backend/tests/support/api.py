"""Helpers for the API tests."""

from typing import Any

from fastapi.testclient import TestClient


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def ir(language: dict[str, Any], symbols: str = "ab") -> dict[str, Any]:
    return {"alphabet": {"symbols": list(symbols), "source": "user"}, "language": language}


def build(client: TestClient, language: dict[str, Any], symbols: str = "ab") -> str:
    response = client.post("/v1/automata", json=ir(language, symbols))
    assert response.status_code == 200, response.json()
    return str(response.json()["automaton_id"])


def error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.json()
    body = response.json()["error"]
    assert body["code"] == code
    assert body["message"]
    return dict(body)
