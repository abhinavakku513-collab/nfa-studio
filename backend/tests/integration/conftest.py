"""A test client on fresh stores and a controllable clock, shared by the API tests."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nfa_studio.api.app import app
from nfa_studio.api.deps import (
    TokenBucket,
    get_automata,
    get_by_spec,
    get_limiter,
    get_llm,
    get_llm_limiter,
    get_sessions,
)
from nfa_studio.ir.limits import LIMITS
from nfa_studio.session.store import TTLStore
from tests.support.api import Clock


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(clock: Clock) -> Iterator[TestClient]:
    """Fresh stores on a controllable clock, and limiters that never refuse."""
    sessions: TTLStore[str, Any] = TTLStore(LIMITS.session_ttl_seconds, clock=clock)
    automata: TTLStore[str, Any] = TTLStore(LIMITS.automaton_ttl_seconds, clock=clock)
    by_spec: TTLStore[str, str] = TTLStore(LIMITS.automaton_ttl_seconds, clock=clock)
    app.dependency_overrides.update(
        {
            get_sessions: lambda: sessions,
            get_automata: lambda: automata,
            get_by_spec: lambda: by_spec,
            get_limiter: lambda: TokenBucket(10**6, 10**6),
            get_llm: lambda: None,
            get_llm_limiter: lambda: TokenBucket(10**6, 10**6),
        }
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
