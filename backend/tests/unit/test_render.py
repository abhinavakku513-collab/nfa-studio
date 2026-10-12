import subprocess
import xml.etree.ElementTree as ET
from typing import Any

import pytest

from nfa_studio.compile import compile
from nfa_studio.compile.naming import name_states
from nfa_studio.compile.regex_parser import parse_regex
from nfa_studio.compile.thompson import thompson
from nfa_studio.core.model import EPS, Automaton, model_hash
from nfa_studio.ir.limits import TimeBudgetExceeded
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.render import RenderMismatch, ensure_consistent
from nfa_studio.render.dot import dot_source
from nfa_studio.render.json_graph import diagram_graph, graph_json
from nfa_studio.render.svg import GraphvizUnavailable, render_diagram, run_dot
from nfa_studio.render.table import (
    build_table,
    table_csv,
    table_json,
    table_latex,
    table_markdown,
)
from tests.support.machines import machine

XLINK_TITLE = "{http://www.w3.org/1999/xlink}title"


def compiled(language: dict[str, Any], symbols: str = "ab") -> Automaton:
    doc = validate_ir(
        {"alphabet": {"symbols": list(symbols), "source": "user"}, "language": language}
    )
    return compile(doc).automaton


ENDS_WITH_AB = compiled({"type": "ends_with", "pattern": "ab"})
AVOIDS_AA = compiled({"type": "avoids", "pattern": "aa"})
# Thompson's machine before ε-removal: compile() never returns ε edges now (C19), but the
# renderers still draw them for any ε-NFA, as the ε-free view's input shows.
AB_STAR = name_states(thompson(parse_regex("(ab)*"), ("a", "b")))


def svg_ids(auto: Automaton, **options: bool) -> tuple[str, set[str]]:
    svg = render_diagram(auto, **options).content.decode("utf-8")
    return svg, {e.get("id", "") for e in ET.fromstring(svg.encode("utf-8")).iter()}


def expected_edge_ids(auto: Automaton, hidden: frozenset[str] = frozenset()) -> set[str]:
    return {
        f"{'ee' if a == EPS else 'e'}-{q}-{r}"
        for (q, a), dsts in auto.delta.items()
        for r in dsts
        if q not in hidden and r not in hidden
    }


def test_spec_7_5_table() -> None:
    table = build_table(ENDS_WITH_AB)
    assert table.columns == ("a", "b")
    assert table_markdown(table) == (
        "| | State | a | b |\n"
        "|---|---|---|---|\n"
        "| → | q0 | {q0, q1} | {q0} |\n"
        "|  | q1 | ∅ | {q2} |\n"
        "| \\* | q2 | ∅ | ∅ |\n"
    )
    assert table_csv(table) == ('marker,state,a,b\n→,q0,"{q0, q1}",{q0}\n,q1,∅,{q2}\n*,q2,∅,∅\n')


def test_epsilon_column_only_when_the_machine_has_epsilon_edges() -> None:
    assert build_table(AB_STAR).columns == ("a", "b", "ε")
    assert build_table(AB_STAR, eps_free=True).columns == ("a", "b")
    assert build_table(ENDS_WITH_AB).columns == ("a", "b")


def test_markers_for_start_accepting_and_both() -> None:
    markers = {row.state: row.marker for row in build_table(AVOIDS_AA).rows}
    assert markers == {"q0": "→*", "q1": "*"}
    rows = table_json(build_table(ENDS_WITH_AB))["rows"]
    assert [(r["marker"], r["start"], r["accepting"]) for r in rows] == [
        ("→", True, False),
        ("", False, False),
        ("*", False, True),
    ]


def test_destination_sets_are_in_naming_order() -> None:
    auto = Automaton(
        states=tuple(f"q{i}" for i in range(11)),
        alphabet=("a",),
        delta={("q0", "a"): frozenset({"q10", "q2"})},
        start="q0",
        final=frozenset({"q2", "q10"}),
    )
    assert build_table(auto).rows[0].cells[0] == ("q2", "q10")
    assert "{q2, q10}" in table_markdown(build_table(auto))


def test_dead_states_are_hidden_unless_asked_for() -> None:
    hidden = build_table(AVOIDS_AA)
    assert [row.state for row in hidden.rows] == ["q0", "q1"]
    assert hidden.rows[1].cells == ((), ("q0",))
    assert hidden.hidden == ("q2",)
    shown = build_table(AVOIDS_AA, show_dead=True)
    assert [row.state for row in shown.rows] == ["q0", "q1", "q2"]
    assert shown.rows[1].cells == (("q2",), ("q0",))


def test_a_dead_start_state_is_still_shown() -> None:
    empty = compiled(
        {
            "type": "and",
            "children": [
                {"type": "starts_with", "pattern": "a"},
                {"type": "starts_with", "pattern": "b"},
            ],
        }
    )
    assert [row.state for row in build_table(empty).rows] == [empty.start]
    assert [node.name for node in diagram_graph(empty).nodes] == [empty.start]


def test_latex_writes_epsilon_empty_set_and_arrows_as_math() -> None:
    latex = table_latex(build_table(AB_STAR))
    assert r"$\varepsilon$" in latex
    assert r"$\emptyset$" in latex
    assert r"$\rightarrow$ & $q_{0}$" in latex
    assert r"$\{q_{1}, q_{2}\}$" in latex
    assert not set("ε∅→") & set(latex)
    assert latex.startswith(r"\begin{tabular}{ll|ccc}")


def test_latex_escapes_special_symbols() -> None:
    auto = machine(
        [("q0", "#", "q1"), ("q0", "&", "q0"), ("q1", "_", "q1")],
        final={"q1"},
        alphabet=("#", "&", "_"),
    )
    header = table_latex(build_table(auto)).splitlines()[1]
    assert header == r" & State & \# & \& & \_ \\"


def test_graph_merges_symbols_and_keeps_epsilon_edges_apart() -> None:
    auto = machine([("q0", "a", "q1"), ("q0", "b", "q1"), ("q0", "ε", "q1")], final={"q1"})
    graph = graph_json(diagram_graph(auto))
    edges = {(e["id"], e["label"], e["epsilon"]) for e in graph["edges"]}
    assert edges == {("e-q0-q1", "a, b", False), ("ee-q0-q1", "ε", True)}
    assert graph["id_map"]["transitions"] == {
        "q0|a|q1": "e-q0-q1",
        "q0|b|q1": "e-q0-q1",
        "q0|ε|q1": "ee-q0-q1",
    }
    assert graph["start_edge"] == {"id": "start-edge", "target": "q0"}


def test_long_meanings_are_shortened_for_the_diagram_only() -> None:
    meaning = "x" * 100
    auto = machine([("q0", "a", "q0")], final={"q0"}, meanings={"q0": meaning})
    node = graph_json(diagram_graph(auto))["nodes"][0]
    assert node["meaning"] == meaning
    assert len(node["short_meaning"]) == 80 and node["short_meaning"].endswith("…")


def test_dot_follows_the_diagram_contract() -> None:
    dot = dot_source(diagram_graph(AB_STAR))
    assert 'graph [rankdir=LR, bgcolor="transparent", nodesep=0.5, ranksep=0.7];' in dot
    assert '"__start" [shape=none, label="", width=0, height=0];' in dot
    assert '"__start" -> "q0" [id="start-edge"];' in dot
    # Thompson's start state accepts only through its ε-closure, so it is a plain circle.
    assert '"q0" [id="s-q0", class="state", shape=circle' in dot
    assert '[id="s-q2", class="state accepting", shape=doublecircle' in dot
    assert '[id="ee-q0-q1", label="ε", style=dashed];' in dot


@pytest.mark.parametrize("auto", [ENDS_WITH_AB, AVOIDS_AA, AB_STAR], ids=["7.5", "7.6", "thompson"])
def test_every_svg_carries_the_contract_ids(auto: Automaton) -> None:
    svg, ids = svg_ids(auto)
    assert {"s-q0", "start-edge"} <= ids
    assert expected_edge_ids(auto, auto.dead) <= ids
    # Readable as text too, not only through an XML parser.
    assert 'id="s-q0"' in svg
    assert "&#45;" not in svg


def test_svg_with_dead_states_marks_them() -> None:
    svg, ids = svg_ids(AVOIDS_AA, show_dead=True)
    assert expected_edge_ids(AVOIDS_AA) <= ids
    classes = {e.get("id"): e.get("class") for e in ET.fromstring(svg.encode("utf-8")).iter()}
    assert classes["s-q2"] == "node state dead"
    assert classes["s-q0"] == "node state accepting"


def test_tooltips_survive_quotes_and_backslashes() -> None:
    meaning = 'say "hi" \\ to <ε> & go'
    auto = machine([("q0", "a", "q0")], final={"q0"}, meanings={"q0": meaning})
    svg = render_diagram(auto).content
    titles = [e.get(XLINK_TITLE) for e in ET.fromstring(svg).iter() if e.get(XLINK_TITLE)]
    assert titles == [meaning]


def test_png_and_dot_exports() -> None:
    png = render_diagram(ENDS_WITH_AB, "png")
    assert png.media_type == "image/png"
    assert png.content.startswith(b"\x89PNG")
    dot = render_diagram(ENDS_WITH_AB, "dot")
    assert dot.media_type == "text/vnd.graphviz"
    assert dot.content.decode("utf-8") == dot_source(diagram_graph(ENDS_WITH_AB))


def test_every_view_reports_the_automaton_id() -> None:
    automaton_id = model_hash(AB_STAR)
    views = [
        build_table(AB_STAR),
        build_table(AB_STAR, eps_free=True, show_dead=True),
        diagram_graph(AB_STAR, eps_free=True),
        render_diagram(AB_STAR),
        render_diagram(AB_STAR, "dot"),
    ]
    assert all(view.model_hash == automaton_id for view in views)
    ensure_consistent(automaton_id, *views)


def test_a_view_of_another_machine_is_refused() -> None:
    with pytest.raises(RenderMismatch, match="were built from"):
        ensure_consistent(model_hash(AB_STAR), build_table(AB_STAR), build_table(ENDS_WITH_AB))


def test_missing_graphviz_is_reported_not_worked_around(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("dot")

    run_dot.cache_clear()
    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(GraphvizUnavailable, match="dot -V"):
        run_dot(b"digraph { a }", "svg")


def test_slow_layout_becomes_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("dot", 10)

    run_dot.cache_clear()
    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(TimeBudgetExceeded, match="Use the transition table") as caught:
        run_dot(b"digraph { b }", "svg")
    assert caught.value.code == "E_TIMEOUT"
