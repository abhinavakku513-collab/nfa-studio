from fastapi.testclient import TestClient

from nfa_studio.api.app import app, cors_origins
from nfa_studio.ir.limits import LIMITS

client = TestClient(app)


def test_health() -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_capabilities_reports_versions_nodes_and_limits() -> None:
    body = client.get("/v1/capabilities").json()
    assert body["api_version"] == "v1"
    assert body["ir_version"] == "1.0"
    assert len(body["node_types"]) == 15
    assert {"and", "or", "not", "regex", "pattern_count"} <= set(body["node_types"])
    assert body["limits"]["max_states"] == LIMITS.max_states == 200
    assert body["limits"]["max_nodes"] == 40
    assert body["limits"]["max_word_len"] == 10_000


def test_cors_allows_only_the_dev_frontend() -> None:
    allowed = client.get("/v1/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"

    other = client.get("/v1/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_cors_origins_come_from_a_comma_separated_list() -> None:
    assert cors_origins(None) == ["http://localhost:3000"]
    assert cors_origins(" , ") == ["http://localhost:3000"]
    assert cors_origins("https://nfa.vercel.app/, http://localhost:3000") == [
        "https://nfa.vercel.app",
        "http://localhost:3000",
    ]
