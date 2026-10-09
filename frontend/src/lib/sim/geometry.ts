export type EdgeShape = {
  group: SVGGElement;
  path: SVGGeometryElement;
  length: number;
};
export type StateShape = {
  group: SVGGElement;
  cx: number;
  cy: number;
  r: number;
};

/** What the animation needs from one rendered diagram, measured once. */
export type Geometry = {
  /** The Graphviz root group; tokens and effects are drawn in its coordinates. */
  layer: SVGGElement;
  edges: ReadonlyMap<string, EdgeShape>;
  states: ReadonlyMap<string, StateShape>;
};

/**
 * Read the edge paths (with their lengths) and state circles of the inlined diagram,
 * using the ids of the diagram contract (spec §10.2). Path lengths are measured
 * here and never during animation, so frames do no layout work.
 */
export function measureDiagram(svg: SVGSVGElement): Geometry | null {
  const layer = svg.querySelector<SVGGElement>("g.graph");
  if (!layer) {
    return null;
  }
  const edges = new Map<string, EdgeShape>();
  for (const group of Array.from(
    svg.querySelectorAll<SVGGElement>("g.edge[id]"),
  )) {
    const path = group.querySelector<SVGGeometryElement>("path");
    // jsdom has no SVG geometry; the diagram then animates states only.
    if (path && typeof path.getTotalLength === "function") {
      edges.set(group.id, { group, path, length: path.getTotalLength() });
    }
  }
  const states = new Map<string, StateShape>();
  for (const group of Array.from(
    svg.querySelectorAll<SVGGElement>("g.state[id]"),
  )) {
    const circles = Array.from(group.querySelectorAll("ellipse"));
    if (circles.length === 0) {
      continue;
    }
    const number = (name: string) => Number(circles[0].getAttribute(name));
    states.set(group.id.replace(/^s-/, ""), {
      group,
      cx: number("cx"),
      cy: number("cy"),
      r: Math.max(...circles.map((c) => Number(c.getAttribute("rx")))),
    });
  }
  return { layer, edges, states };
}

/** A point `t` (0 to 1) of the way along an edge. */
export function pointOn(shape: EdgeShape, t: number): { x: number; y: number } {
  const point = shape.path.getPointAtLength(t * shape.length);
  return { x: point.x, y: point.y };
}
