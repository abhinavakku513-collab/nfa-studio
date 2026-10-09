"""Transition table and its JSON, CSV, Markdown and LaTeX exports (spec §10.1)."""

import csv
import io
import re
from dataclasses import dataclass
from typing import Final

from nfa_studio.core.model import EPS, EPS_LABEL, Automaton, display_symbol, has_epsilon, model_hash
from nfa_studio.render import view_of

EMPTY_SET: Final = "∅"
START_MARK: Final = "→"
ACCEPT_MARK: Final = "*"


@dataclass(frozen=True)
class Row:
    state: str
    marker: str
    cells: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Table:
    """One column per symbol in alphabet order, then ε only if the machine has ε edges.

    Each cell is the destination set in naming order; an empty tuple is ∅. Dead
    states are left out of rows and cells unless they were asked for.
    """

    model_hash: str
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    eps_free: bool
    hidden: tuple[str, ...]


def build_table(auto: Automaton, *, eps_free: bool = False, show_dead: bool = False) -> Table:
    read = model_hash(auto)
    view = view_of(auto, eps_free)
    # The start state stays even when dead, or an empty language would have no table.
    hidden = () if show_dead else view.ordered(view.dead - {view.start})
    shown = [q for q in view.states if q not in hidden]
    labels = list(view.alphabet) + ([EPS] if has_epsilon(view) else [])
    rows = tuple(
        Row(
            state=q,
            marker=_marker(q == view.start, q in view.final),
            cells=tuple(
                tuple(r for r in view.ordered(view.targets(q, a)) if r not in hidden)
                for a in labels
            ),
        )
        for q in shown
    )
    columns = tuple(display_symbol(a) for a in labels)
    return Table(read, columns, rows, eps_free, tuple(hidden))


def _marker(start: bool, accepting: bool) -> str:
    return (START_MARK if start else "") + (ACCEPT_MARK if accepting else "")


def table_json(table: Table) -> dict[str, object]:
    return {
        "model_hash": table.model_hash,
        "eps_free": table.eps_free,
        "columns": list(table.columns),
        "rows": [
            {
                "state": row.state,
                "marker": row.marker,
                "start": START_MARK in row.marker,
                "accepting": ACCEPT_MARK in row.marker,
                "cells": [list(cell) for cell in row.cells],
            }
            for row in table.rows
        ],
        "hidden_dead_states": list(table.hidden),
    }


def _set_text(cell: tuple[str, ...]) -> str:
    return "{" + ", ".join(cell) + "}" if cell else EMPTY_SET


def table_csv(table: Table) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["marker", "state", *table.columns])
    for row in table.rows:
        writer.writerow([row.marker, row.state, *map(_set_text, row.cells)])
    return out.getvalue()


def table_markdown(table: Table) -> str:
    def escape(text: str) -> str:
        # * and | are not alphabet symbols (CLAUDE.md item 3) but * is the accept marker.
        return text.replace("*", "\\*")

    lines = [
        "| | State | " + " | ".join(table.columns) + " |",
        "|---|---|" + "---|" * len(table.columns),
    ]
    for row in table.rows:
        cells = " | ".join(_set_text(cell) for cell in row.cells)
        lines.append(f"| {escape(row.marker)} | {row.state} | {cells} |")
    return "\n".join(lines) + "\n"


_LATEX_SPECIALS: Final = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def table_latex(table: Table) -> str:
    """A `tabular` with →, *, ε and ∅ written as math, and symbols escaped for text mode."""
    header = " & ".join(
        r"$\varepsilon$" if c == EPS_LABEL else _latex_text(c) for c in table.columns
    )
    lines = [
        r"\begin{tabular}{ll|" + "c" * len(table.columns) + "}",
        rf" & State & {header} \\",
        r"\hline",
    ]
    for row in table.rows:
        marker = {"": "", "→": r"$\rightarrow$", "*": r"$*$", "→*": r"$\rightarrow *$"}[row.marker]
        cells = " & ".join(_latex_set(cell) for cell in row.cells)
        lines.append(rf"{marker} & ${_latex_state(row.state)}$ & {cells} \\")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def _latex_set(cell: tuple[str, ...]) -> str:
    if not cell:
        return r"$\emptyset$"
    return r"$\{" + ", ".join(_latex_state(q) for q in cell) + r"\}$"


def _latex_state(name: str) -> str:
    """q12 → q_{12}; any other name as escaped upright text."""
    if m := re.fullmatch(r"([A-Za-z]+)(\d+)", name):
        return f"{m[1]}_{{{m[2]}}}"
    return r"\text{" + _latex_text(name) + "}"


def _latex_text(text: str) -> str:
    return "".join(_LATEX_SPECIALS.get(c, c) for c in text)
