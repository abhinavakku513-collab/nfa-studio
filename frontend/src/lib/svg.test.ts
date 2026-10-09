import { describe, expect, it } from "vitest";
import { labelDiagram, sanitizeSvg, svgSize } from "./svg";

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="300pt" height="90pt" viewBox="0 0 300 90" onload="alert(1)">
<script>alert(2)</script>
<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">html</div></foreignObject>
<g id="s-q0" class="node state" onmouseover="alert(3)">
<a xlink:href="javascript:alert(4)" xlink:title="start"><ellipse cx="10" cy="10" rx="5" ry="5"/></a>
</g>
<g id="a_s-q1"><a xlink:title="no a seen yet"><text>q1</text></a></g>
</svg>`;

describe("sanitizeSvg", () => {
  it("strips scripts, foreign objects, handlers and javascript: links", () => {
    const clean = sanitizeSvg(SVG);
    expect(clean).not.toMatch(
      /<script|foreignObject|onload|onmouseover|javascript:/i,
    );
    expect(clean).toContain('id="s-q0"');
    expect(clean).toContain('xlink:title="no a seen yet"');
    expect(clean).toContain('role="img"');
  });

  it("drops the fixed size so the drawing scales, keeping the viewBox", () => {
    const clean = sanitizeSvg(SVG);
    expect(clean).not.toMatch(/<svg[^>]*\swidth=/);
    expect(svgSize(clean)).toEqual({ width: 300, height: 90 });
  });

  it("refuses a document that is not SVG", () => {
    expect(() => sanitizeSvg("<html><body>hi</body></html>")).toThrow(
      "The diagram is not an SVG document.",
    );
  });
});

describe("labelDiagram", () => {
  const graph = {
    model_hash: "sha256:abc",
    eps_free: false,
    start_edge: { id: "start-edge", target: "q0" },
    nodes: [
      {
        id: "s-q0",
        name: "q0",
        start: true,
        accepting: false,
        dead: false,
        meaning: "nothing read",
        short_meaning: "nothing read",
      },
      {
        id: "s-q1",
        name: "q1",
        start: false,
        accepting: true,
        dead: false,
        meaning: "read a",
        short_meaning: "read a",
      },
    ],
    edges: [
      {
        id: "e-q0-q1",
        source: "q0",
        target: "q1",
        symbols: ["a", "b"],
        label: "a, b",
        epsilon: false,
      },
      {
        id: "ee-q1-q0",
        source: "q1",
        target: "q0",
        symbols: ["ε"],
        label: "ε",
        epsilon: true,
      },
    ],
    id_map: { states: {}, transitions: {} },
    hidden_dead_states: [],
  };
  const drawing =
    sanitizeSvg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 9 9">
<g id="start-edge" class="edge"><path d="M0,0"/></g>
<g id="s-q0" class="node state"><title>q0</title></g>
<g id="s-q1" class="node state accepting"><title>q1</title></g>
<g id="e-q0-q1" class="edge"><path d="M0,0"/></g>
<g id="ee-q1-q0" class="edge"><path d="M0,0"/></g>
</svg>`);

  it("names the drawing, every state and every edge", () => {
    const doc = new DOMParser().parseFromString(
      labelDiagram(drawing, graph),
      "image/svg+xml",
    );
    const root = doc.documentElement;
    expect(root.getAttribute("role")).toBe("group");
    expect(root.getAttribute("aria-label")).toBe(
      "Automaton with 2 states, start state q0, accepting q1",
    );
    const named = Array.from(root.querySelectorAll("[role=img]")).map((g) =>
      g.getAttribute("aria-label"),
    );
    expect(named).toEqual([
      "q0, start state: nothing read",
      "q1, accepting state: read a",
      "transition from q0 to q1 on a, b",
      "ε-transition from q1 to q0",
    ]);
    expect(
      root.querySelector('[id="start-edge"]')?.getAttribute("aria-hidden"),
    ).toBe("true");
  });
});
