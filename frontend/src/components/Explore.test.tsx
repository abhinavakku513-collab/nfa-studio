import { readFileSync } from "node:fs";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { StudioProvider } from "@/lib/studio/context";
import { type Handler, fakeServer } from "@/test/fakeServer";
import { DiagramTab } from "./DiagramTab";
import { FormalTab } from "./FormalTab";
import { TableTab } from "./TableTab";

const ID = "sha256:abc123";
const BASE = `/v1/automata/${ID}`;

type Row = [marker: string, state: string, cells: string[][]];

function table(columns: string[], rows: Row[]) {
  return {
    model_hash: ID,
    eps_free: !columns.includes("ε"),
    columns,
    rows: rows.map(([marker, state, cells]) => ({
      state,
      marker,
      start: marker.includes("→"),
      accepting: marker.includes("*"),
      cells,
    })),
    hidden_dead_states: [],
  };
}

function renderWith(routes: Record<string, Handler>, ui: ReactNode) {
  const server = fakeServer(routes);
  const { container } = render(
    <StudioProvider api={server.api}>{ui}</StudioProvider>,
  );
  return { ...server, container };
}

function rowOf(state: string): HTMLTableRowElement {
  const row = screen.getByRole("rowheader", { name: state }).closest("tr");
  if (!row) {
    throw new Error(`no row for ${state}`);
  }
  return row;
}

function columnHeaders(): string[] {
  return screen
    .getAllByRole("columnheader")
    .map((header) => header.textContent ?? "");
}

describe("TableTab markers", () => {
  it("marks the start state → and accepting states *, and leaves others blank", async () => {
    renderWith(
      {
        [`GET ${BASE}/table`]: () => ({
          json: table(
            ["a", "b"],
            [
              ["→", "q0", [["q1"], []]],
              ["*", "q1", [["q1"], ["q0", "q1"]]],
              ["", "q2", [[], []]],
            ],
          ),
        }),
      },
      <TableTab id={ID} hasEpsilon={false} />,
    );
    await screen.findByRole("table");

    const start = within(rowOf("q0")).getByLabelText("start state");
    expect(start).toHaveTextContent(/^→$/);
    const accepting = within(rowOf("q1")).getByLabelText("accepting state");
    expect(accepting).toHaveTextContent(/^\*$/);
    expect(rowOf("q2").cells[0]).toHaveTextContent(/^$/);

    expect(rowOf("q0").cells[3]).toHaveTextContent("∅");
    expect(rowOf("q1").cells[3]).toHaveTextContent("{q0, q1}");
  });

  it("marks a state that is both start and accepting →*", async () => {
    renderWith(
      {
        [`GET ${BASE}/table`]: () => ({
          json: table(["0", "1"], [["→*", "q0", [["q0"], ["q0"]]]]),
        }),
      },
      <TableTab id={ID} hasEpsilon={false} />,
    );
    await screen.findByRole("table");
    expect(
      within(rowOf("q0")).getByLabelText("start and accepting state"),
    ).toHaveTextContent(/^→\*$/);
  });

  it("shows an ε column only when the machine has ε moves", async () => {
    const queries: string[] = [];
    renderWith(
      {
        [`GET ${BASE}/table`]: (_, url) => {
          queries.push(url.search);
          const epsFree = url.searchParams.get("eps_free") === "true";
          return {
            json: epsFree
              ? table(["a"], [["→*", "q0", [["q0"]]]])
              : table(
                  ["a", "ε"],
                  [
                    ["→", "q0", [[], ["q1"]]],
                    ["*", "q1", [["q1"], []]],
                  ],
                ),
          };
        },
      },
      <TableTab id={ID} hasEpsilon />,
    );
    await screen.findByRole("table");
    expect(columnHeaders()).toEqual(["Marker", "State", "a", "ε"]);

    fireEvent.click(screen.getByRole("switch", { name: "ε-free version" }));
    await waitFor(() =>
      expect(columnHeaders()).toEqual(["Marker", "State", "a"]),
    );
    expect(queries.at(-1)).toContain("eps_free=true");
  });

  it("offers no ε-free toggle for a machine without ε moves", async () => {
    renderWith(
      {
        [`GET ${BASE}/table`]: () => ({
          json: table(["a"], [["→*", "q0", [["q0"]]]]),
        }),
      },
      <TableTab id={ID} hasEpsilon={false} />,
    );
    await screen.findByRole("table");
    expect(columnHeaders()).toEqual(["Marker", "State", "a"]);
    expect(
      screen.queryByRole("switch", { name: "ε-free version" }),
    ).not.toBeInTheDocument();
  });
});

const DETAIL = {
  automaton_id: ID,
  kind: "enfa",
  state_count: 2,
  five_tuple: {
    Q: ["q0", "q1"],
    Sigma: ["a", "b"],
    delta: [
      ["q0", "ε", ["q1"]],
      ["q1", "a", ["q1"]],
    ],
    q0: "q0",
    F: ["q1"],
  },
  meanings: { q0: "start", q1: "seen only a's" },
  dead: [],
};

/** The font stacks of globals.css, keyed by Tailwind's font-* utility. */
function fontStacks(): Record<string, string> {
  const css = readFileSync("src/app/globals.css", "utf8");
  const stacks: Record<string, string> = {};
  for (const [, name, stack] of css.matchAll(
    /--font-(sans|mono|math):\s*([^;]+);/g,
  )) {
    stacks[name] = stack.replace(/\s+/g, " ").trim();
  }
  return stacks;
}

/** The font utility in effect for an element; the body uses the sans stack. */
function fontOf(element: Element): string {
  for (let node: Element | null = element; node; node = node.parentElement) {
    const match = /(?:^|\s)font-(sans|mono|math)(?:\s|$)/.exec(
      node.getAttribute("class") ?? "",
    );
    if (match) {
      return match[1];
    }
  }
  return "sans";
}

/** Elements whose own text (not a descendant's) contains `glyph`. */
function rendering(root: Element, glyph: string): Element[] {
  return [root, ...Array.from(root.querySelectorAll("*"))].filter((element) =>
    Array.from(element.childNodes).some(
      (node) =>
        node.nodeType === Node.TEXT_NODE && node.textContent?.includes(glyph),
    ),
  );
}

describe("glyph check (spec §12.2)", () => {
  it("loads Noto Sans Math from next/font as --font-noto-sans-math", () => {
    const layout = readFileSync("src/app/layout.tsx", "utf8");
    expect(layout).toMatch(
      /Noto_Sans_Math\(\{\s*variable: "--font-noto-sans-math"/,
    );
    expect(layout).toContain("${notoSansMath.variable}");
  });

  it("renders ε δ Σ ∅ q₀ →* only in font stacks that fall back to Noto Sans Math", async () => {
    const { container } = renderWith(
      {
        [`GET ${BASE}`]: () => ({ json: DETAIL }),
        [`GET ${BASE}/table`]: () => ({
          json: table(
            ["a", "b", "ε"],
            [
              ["→*", "q0", [[], [], ["q1"]]],
              ["*", "q1", [["q1"], [], []]],
            ],
          ),
        }),
      },
      <>
        <FormalTab id={ID} />
        <TableTab id={ID} hasEpsilon />
      </>,
    );
    await screen.findByText("N = (Q, Σ, δ, q₀, F)", { exact: false });
    await screen.findByRole("table");

    const stacks = fontStacks();
    expect(Object.keys(stacks).sort()).toEqual(["math", "mono", "sans"]);
    for (const glyph of ["ε", "δ", "Σ", "∅", "q₀", "→*"]) {
      const elements = rendering(container, glyph);
      expect(elements.length, `${glyph} is rendered`).toBeGreaterThan(0);
      for (const element of elements) {
        const stack = stacks[fontOf(element)];
        expect(stack, `${glyph} in <${element.tagName}>`).toContain(
          "var(--font-noto-sans-math)",
        );
      }
    }
  });

  it("typesets the formal definition with the math font", async () => {
    renderWith(
      { [`GET ${BASE}`]: () => ({ json: DETAIL }) },
      <FormalTab id={ID} />,
    );
    const tuple = await screen.findByText("N = (Q, Σ, δ, q₀, F)", {
      exact: false,
    });
    expect(fontOf(tuple)).toBe("math");
    const delta = screen.getByText("δ(q₀, ε) = {q₁}");
    expect(fontOf(delta)).toBe("math");
    expect(screen.getByText("= {q₀, q₁}")).toBeInTheDocument();
  });
});

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="80pt" viewBox="0 0 200 80" onload="alert(1)">
<script>alert(2)</script>
<g id="s-q0" class="node state"><title>q0</title><ellipse cx="40" cy="40" rx="18" ry="18" onclick="alert(3)"/><text x="40" y="44">q0</text></g>
<g id="s-q1" class="node state accepting"><title>q1</title><ellipse cx="140" cy="40" rx="18" ry="18"/><text x="140" y="44">q1</text></g>
</svg>`;

const GRAPH = {
  model_hash: ID,
  eps_free: false,
  start_edge: { id: "start-edge", target: "q0" },
  nodes: [
    {
      id: "s-q0",
      name: "q0",
      start: true,
      accepting: false,
      dead: false,
      meaning: "no a seen yet",
      short_meaning: "no a seen yet",
    },
    {
      id: "s-q1",
      name: "q1",
      start: false,
      accepting: true,
      dead: false,
      meaning: "at least one a seen",
      short_meaning: "at least one a seen",
    },
  ],
  edges: [],
  id_map: { states: {}, edges: {}, epsilon_edges: {} },
  hidden_dead_states: [],
};

describe("DiagramTab", () => {
  it("inlines the sanitised SVG and explains a state on hover", async () => {
    const { container } = renderWith(
      {
        [`GET ${BASE}/diagram`]: (_, url) =>
          url.searchParams.get("format") === "svg"
            ? { text: SVG, type: "image/svg+xml" }
            : { json: GRAPH },
      },
      <DiagramTab id={ID} hasEpsilon={false} />,
    );
    const diagram = await screen.findByRole("group", {
      name: "Automaton with 2 states, start state q0, accepting q1",
    });
    expect(diagram.querySelector("script")).toBeNull();
    expect(container.querySelector("[onload], [onclick]")).toBeNull();
    expect(diagram).not.toHaveAttribute("width");
    // spec §12.2: every state has a text alternative with its role and meaning.
    expect(
      within(diagram)
        .getAllByRole("img")
        .map((node) => node.getAttribute("aria-label")),
    ).toEqual([
      "q0, start state: no a seen yet",
      "q1, accepting state: at least one a seen",
    ]);

    const legend = await screen.findByRole("region", {
      name: "States and their meanings",
    });
    expect(legend).toHaveTextContent("at least one a seen");

    const state = container.querySelector('[id="s-q1"] text');
    if (!state) {
      throw new Error("state q1 is not in the diagram");
    }
    fireEvent.pointerOver(state);
    expect(screen.getByText(/^: at least one a seen$/)).toBeInTheDocument();
    expect(container.querySelector('[id="s-q1"]')).toHaveClass(
      "is-highlighted",
    );

    const [first] = within(legend).getAllByRole("listitem");
    expect(first).toHaveTextContent("no a seen yet");
    fireEvent.focus(first);
    expect(container.querySelector('[id="s-q0"]')).toHaveClass(
      "is-highlighted",
    );
    expect(container.querySelector('[id="s-q1"]')).not.toHaveClass(
      "is-highlighted",
    );
  });
});
