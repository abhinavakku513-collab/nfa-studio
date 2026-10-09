"""DOT source following the diagram contract in CLAUDE.md (spec §10.2)."""

from nfa_studio.render.json_graph import START_EDGE_ID, DiagramGraph


def dot_source(graph: DiagramGraph) -> str:
    """Graphviz DOT for `graph`; every element carries the id the client animates.

    States are `s-<name>` with class "state" (plus "accepting", "dead"); symbol edges
    are `e-<src>-<dst>` with merged labels; ε edges are separate, dashed, `ee-…`.
    Fonts are left to the client's CSS.
    """
    lines = [
        "digraph nfa {",
        '  graph [rankdir=LR, bgcolor="transparent", nodesep=0.5, ranksep=0.7];',
        '  "__start" [shape=none, label="", width=0, height=0];',
    ]
    for node in graph.nodes:
        classes = " ".join(["state"] + ["accepting"] * node.accepting + ["dead"] * node.dead)
        shape = "doublecircle" if node.accepting else "circle"
        lines.append(
            f"  {_quote(node.name)} [id={_quote(node.id)}, class={_quote(classes)}, "
            f"shape={shape}, label={_quote(node.name)}, tooltip={_quote(node.meaning)}];"
        )
    lines.append(f'  "__start" -> {_quote(graph.start)} [id={_quote(START_EDGE_ID)}];')
    for edge in graph.edges:
        style = ", style=dashed" if edge.epsilon else ""
        lines.append(
            f"  {_quote(edge.source)} -> {_quote(edge.target)} "
            f"[id={_quote(edge.id)}, label={_quote(edge.label)}{style}];"
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _quote(text: str) -> str:
    """A DOT double-quoted string; backslashes are doubled so no escape sequence fires."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'
