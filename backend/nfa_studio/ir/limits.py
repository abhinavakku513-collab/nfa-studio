"""Every hard limit in the system and the budget that enforces the construction limits.

/v1/capabilities publishes `LIMITS` (spec §5.3).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Limits:
    """Size, time and input limits from spec §5.3, §7.3, §8.2 and §9.3."""

    # spec §5.3: IR size
    max_nodes: int = 40
    max_pattern_len: int = 16
    max_count: int = 20
    max_regex_len: int = 200
    min_alphabet_size: int = 1
    max_alphabet_size: int = 6

    # spec §7.3: state-explosion policy for determinize, product and complement
    max_states: int = 200
    time_budget_seconds: float = 2.0

    # spec §9.3: simulation
    max_word_len: int = 10_000
    trace_page_size: int = 200
    max_batch_size: int = 100

    # spec §8.2 and CLAUDE.md C7–C9: verification
    reference_max_states: int = 2_000
    bounded_max_words: int = 200_000
    bounded_max_length: int = 10
    property_words: int = 500
    property_max_length: int = 30


LIMITS = Limits()


class StateLimitExceeded(Exception):
    code: ClassVar[str] = "E_STATE_LIMIT"

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(
            f"The construction reached {size} states, more than the limit of {limit}. "
            "Simplify the description, shorten the patterns, or split the request."
        )
        self.size = size
        self.limit = limit


class TimeBudgetExceeded(Exception):
    code: ClassVar[str] = "E_TIMEOUT"

    def __init__(self, seconds: float) -> None:
        super().__init__(
            f"The construction took longer than {seconds:g} s. "
            "Simplify the description or split the request."
        )
        self.seconds = seconds


class Budget:
    """State cap and wall-clock deadline shared by one construction (spec §7.3).

    Checked from inside the construction loops with `time.monotonic()`: threads and
    signals cannot interrupt work portably, and signals do not exist on Windows.
    """

    def __init__(
        self,
        max_states: int = LIMITS.max_states,
        seconds: float = LIMITS.time_budget_seconds,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_states = max_states
        self.seconds = seconds
        self._clock = clock
        self._deadline = clock() + seconds

    def check(self, size: int) -> None:
        """Raise if a machine of `size` states is too big or the deadline has passed."""
        if size > self.max_states:
            raise StateLimitExceeded(size, self.max_states)
        self.check_time()

    def check_time(self) -> None:
        if self._clock() > self._deadline:
            raise TimeBudgetExceeded(self.seconds)
