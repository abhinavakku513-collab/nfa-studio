"""Graphviz layout to SVG and PNG, and the DOT export (spec §10.2)."""

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from nfa_studio.core.model import Automaton
from nfa_studio.ir.limits import LIMITS, TimeBudgetExceeded
from nfa_studio.render.dot import dot_source
from nfa_studio.render.json_graph import diagram_graph

DiagramFormat = Literal["svg", "png", "dot"]

MEDIA_TYPES: dict[DiagramFormat, str] = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "dot": "text/vnd.graphviz",
}


class GraphvizUnavailable(RuntimeError):
    """`dot` is not on PATH; CLAUDE.md forbids falling back to another layout engine."""


@dataclass(frozen=True)
class Diagram:
    content: bytes
    media_type: str
    model_hash: str


def render_diagram(
    auto: Automaton,
    fmt: DiagramFormat = "svg",
    *,
    show_dead: bool = False,
    eps_free: bool = False,
) -> Diagram:
    graph = diagram_graph(auto, show_dead=show_dead, eps_free=eps_free)
    source = dot_source(graph).encode("utf-8")
    content = source if fmt == "dot" else run_dot(source, fmt)
    if fmt == "svg":
        # Graphviz writes "-" in ids as the character reference &#45;. Both mean the
        # same to an XML parser; the literal form also makes `s-q0` searchable as text.
        # It also ends lines with CRLF on Windows; one line ending keeps output portable.
        content = content.replace(b"&#45;", b"-").replace(b"\r\n", b"\n")
    return Diagram(content, MEDIA_TYPES[fmt], graph.model_hash)


@lru_cache(maxsize=256)
def run_dot(source: bytes, fmt: Literal["svg", "png"]) -> bytes:
    """Lay out `source` with Graphviz's dot.

    Cached on the DOT text, which fixes the output completely (meanings included,
    which the model hash leaves out); a layout costs about a second even when small.
    """
    try:
        done = subprocess.run(
            ["dot", f"-T{fmt}"],
            input=source,
            capture_output=True,
            timeout=LIMITS.render_timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GraphvizUnavailable(
            "Graphviz's dot is not on PATH; install Graphviz and check that `dot -V` works."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        seconds = LIMITS.render_timeout_seconds
        raise TimeBudgetExceeded(
            seconds,
            f"Graphviz could not lay out this diagram within {seconds:g} s. "
            "Use the transition table, or simplify the description.",
        ) from exc
    if done.returncode != 0:
        raise RuntimeError(f"dot failed: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout
