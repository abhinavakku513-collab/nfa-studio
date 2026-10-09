"""The diagram as data: states, merged edges and their SVG ids (spec §10.2, CLAUDE.md).

The DOT renderer and the client's highlighter both read this one structure, so the
ids in the SVG and the ids the client animates cannot drift apart.
"""

from dataclasses import dataclass
from typing import Final

from nfa_studio.core.model import EPS, EPS_LABEL, Automaton, model_hash
from nfa_studio.render import view_of

START_EDGE_ID: Final = "start-edge"
# C10: meanings longer than this are cut in the diagram; the legend shows them in full.
MEANING_DISPLAY_LIMIT: Final = 80


@dataclass(frozen=True)
class GraphNode:
    name: str
    id: str
    start: bool
    accepting: bool
    dead: bool
    meaning: str


@dataclass(frozen=True)
class GraphEdge:
    """All symbol edges from one state to another, or the ε edge between them."""

    id: str
    source: str
    target: str
    symbols: tuple[str, ...]

    @property
    def epsilon(self) -> bool:
        return self.symbols == (EPS,)

    @property
    def label(self) -> str:
        return EPS_LABEL if self.epsilon else ", ".join(self.symbols)


@dataclass(frozen=True)
class DiagramGraph:
    model_hash: str
    start: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    eps_free: bool
    hidden: tuple[str, ...]


def state_id(name: str) -> str:
    return f"s-{name}"


def edge_id(source: str, target: str, epsilon: bool) -> str:
    return f"{'ee' if epsilon else 'e'}-{source}-{target}"


def diagram_graph(
    auto: Automaton, *, show_dead: bool = False, eps_free: bool = False
) -> DiagramGraph:
    """Visible states in naming order and one edge per (source, target, ε or not).

    Symbols on one edge are in alphabet order. Edges are ordered by source, then
    target, in naming order, with the symbol edge before the ε edge. Dead states and
    their edges are hidden unless asked for; the start state is always shown.
    """
    read = model_hash(auto)
    view = view_of(auto, eps_free)
    hidden = () if show_dead else view.ordered(view.dead - {view.start})
    nodes = tuple(
        GraphNode(
            name=q,
            id=state_id(q),
            start=q == view.start,
            accepting=q in view.final,
            dead=q in view.dead,
            meaning=view.meaning(q),
        )
        for q in view.states
        if q not in hidden
    )
    labels: dict[tuple[str, str, bool], list[str]] = {}
    for q in view.states:
        for a in (*view.alphabet, EPS):
            for r in view.targets(q, a):
                labels.setdefault((q, r, a == EPS), []).append(a)
    edges = tuple(
        GraphEdge(edge_id(q, r, eps), q, r, tuple(symbols))
        for (q, r, eps), symbols in sorted(
            labels.items(),
            key=lambda item: (view.index[item[0][0]], view.index[item[0][1]], item[0][2]),
        )
        if q not in hidden and r not in hidden
    )
    return DiagramGraph(read, view.start, nodes, edges, eps_free, tuple(hidden))


def graph_json(graph: DiagramGraph) -> dict[str, object]:
    """Nodes, edges and the id map the client uses to find SVG elements.

    `id_map.transitions` maps "q|a|r" (a = "ε" for ε moves) to the id of the drawn
    edge, so a trace's transitions and ε layers (C2) can be animated directly.
    """
    transitions = {
        f"{edge.source}|{EPS_LABEL if a == EPS else a}|{edge.target}": edge.id
        for edge in graph.edges
        for a in edge.symbols
    }
    return {
        "model_hash": graph.model_hash,
        "eps_free": graph.eps_free,
        "start_edge": {"id": START_EDGE_ID, "target": graph.start},
        "nodes": [
            {
                "id": node.id,
                "name": node.name,
                "start": node.start,
                "accepting": node.accepting,
                "dead": node.dead,
                "meaning": node.meaning,
                "short_meaning": _shorten(node.meaning),
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "symbols": [EPS_LABEL if a == EPS else a for a in edge.symbols],
                "label": edge.label,
                "epsilon": edge.epsilon,
            }
            for edge in graph.edges
        ],
        "id_map": {
            "states": {node.name: node.id for node in graph.nodes},
            "transitions": transitions,
        },
        "hidden_dead_states": list(graph.hidden),
    }


def _shorten(text: str) -> str:
    if len(text) <= MEANING_DISPLAY_LIMIT:
        return text
    return text[: MEANING_DISPLAY_LIMIT - 1] + "…"
