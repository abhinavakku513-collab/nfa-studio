"""Shared state for the API: the stores and the per-IP rate limiter (spec §3.1, §13)."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from nfa_studio.api.errors import ApiError
from nfa_studio.compile import Compiled
from nfa_studio.core.model import Automaton
from nfa_studio.interpret.llm_adapter import LLMTier, tier_from_env
from nfa_studio.ir.limits import LIMITS
from nfa_studio.ir.schema import IRDocument
from nfa_studio.session.clarify import Session
from nfa_studio.session.store import TTLStore
from nfa_studio.verify.ladder import Report


@dataclass(frozen=True)
class StoredAutomaton:
    automaton: Automaton
    spec: IRDocument
    compiled: Compiled
    report: Report


class TokenBucket:
    """Per-key token bucket: `burst` requests at once, refilled at `per_second`.

    Written here rather than pulled from a package; it is a dozen lines.
    """

    def __init__(
        self, burst: int, per_second: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.burst = burst
        self.per_second = per_second
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str) -> float:
        """Spend one token; 0 if allowed, else the seconds until a token is available."""
        with self._lock:
            now = self.clock()
            tokens, last = self._buckets.get(key, (float(self.burst), now))
            tokens = min(float(self.burst), tokens + (now - last) * self.per_second)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return 0.0
            self._buckets[key] = (tokens, now)
            if len(self._buckets) > 100_000:
                self._forget_full(now)
            return (1 - tokens) / self.per_second

    def _forget_full(self, now: float) -> None:
        refill = self.burst / self.per_second
        self._buckets = {k: v for k, v in self._buckets.items() if now - v[1] < refill}


sessions: TTLStore[str, Session] = TTLStore(LIMITS.session_ttl_seconds)
automata: TTLStore[str, StoredAutomaton] = TTLStore(LIMITS.automaton_ttl_seconds)
# spec hash → automaton id: identical specifications are compiled and verified once.
by_spec: TTLStore[str, str] = TTLStore(LIMITS.automaton_ttl_seconds)
limiter = TokenBucket(LIMITS.rate_limit_burst, LIMITS.rate_limit_per_second)
# None unless NFA_LLM_ENABLED=1 (backend/.env or the environment).
llm_tier = tier_from_env()


def get_sessions() -> TTLStore[str, Session]:
    return sessions


def get_automata() -> TTLStore[str, StoredAutomaton]:
    return automata


def get_by_spec() -> TTLStore[str, str]:
    return by_spec


def get_limiter() -> TokenBucket:
    return limiter


def get_llm() -> LLMTier | None:
    return llm_tier


def rate_limit(request: Request, bucket: Annotated[TokenBucket, Depends(get_limiter)]) -> None:
    wait = bucket.take(request.client.host if request.client else "unknown")
    if wait > 0:
        seconds = max(1, round(wait))
        raise ApiError(
            "E_RATE_LIMITED",
            f"Too many requests from this address. Wait {seconds} s and try again.",
            {"retry_after": seconds},
            {"Retry-After": str(seconds)},
        )


Sessions = Annotated[TTLStore[str, Session], Depends(get_sessions)]
Automata = Annotated[TTLStore[str, StoredAutomaton], Depends(get_automata)]
BySpec = Annotated[TTLStore[str, str], Depends(get_by_spec)]
LLM = Annotated[LLMTier | None, Depends(get_llm)]
