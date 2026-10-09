"""In-memory key-value store whose entries expire (spec §3.1: in-memory dict with TTL)."""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLStore(Generic[K, V]):
    """Entries live `ttl` seconds after their last write; the oldest go first when full.

    Entries are kept in write order, so expired ones are always at the front and a
    sweep stops at the first live entry. Safe to share between request threads.
    """

    def __init__(
        self,
        ttl: float,
        capacity: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl = ttl
        self.capacity = capacity
        self.clock = clock
        self._entries: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, key: K, value: V) -> None:
        with self._lock:
            self._sweep()
            self._entries[key] = (self.clock() + self.ttl, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires, value = entry
            if self.clock() >= expires:
                del self._entries[key]
                return None
            return value

    def delete(self, key: K) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def __len__(self) -> int:
        with self._lock:
            self._sweep()
            return len(self._entries)

    def _sweep(self) -> None:
        now = self.clock()
        while self._entries:
            key, (expires, _) = next(iter(self._entries.items()))
            if expires > now:
                break
            del self._entries[key]
