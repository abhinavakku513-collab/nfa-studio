"""Every hard limit in the system; /v1/capabilities publishes these values (spec §5.3)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    """Size, time and input limits from spec §5.3, §7.3 and §9.3."""

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


LIMITS = Limits()
