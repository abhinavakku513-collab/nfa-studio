"""Views of the canonical model: table, DOT/SVG/PNG diagram and JSON graph (spec §10).

Every renderer reads the model itself and reports the hash of what it read, so a view
built from a stale or hand-copied δ cannot pass `ensure_consistent` (spec §10.3).
"""

from typing import Protocol

from nfa_studio.core.determinize import remove_epsilon
from nfa_studio.core.model import Automaton


class HasModelHash(Protocol):
    @property
    def model_hash(self) -> str: ...


class RenderMismatch(RuntimeError):
    """A view was not built from the automaton it claims to show."""


def view_of(auto: Automaton, eps_free: bool) -> Automaton:
    """The machine a view shows: the model itself, or its ε-free version.

    The ε-free version keeps the model's state names, so both views can be compared
    state by state.
    """
    return remove_epsilon(auto) if eps_free else auto


def ensure_consistent(automaton_id: str, *views: HasModelHash) -> None:
    """Refuse to answer when any view read a model other than `automaton_id` (spec §10.3)."""
    stale = sorted({view.model_hash for view in views} - {automaton_id})
    if stale:
        raise RenderMismatch(f"views of {automaton_id} were built from {', '.join(stale)}")
