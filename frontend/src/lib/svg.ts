import type { GraphEdge, GraphModel, GraphNode } from "@/lib/api/client";

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * The diagram SVG with anything executable removed, ready to inline.
 *
 * It comes from our own server, but inlining puts it in the page, so <script>,
 * <foreignObject>, every on* handler and javascript: links are stripped anyway. The
 * fixed width and height go too, so the drawing scales to its panel.
 */
export function sanitizeSvg(text: string): string {
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  const root = doc.documentElement;
  if (root.namespaceURI !== SVG_NS || root.localName !== "svg") {
    throw new Error("The diagram is not an SVG document.");
  }
  for (const element of Array.from(
    root.querySelectorAll("script, foreignObject"),
  )) {
    element.remove();
  }
  for (const element of [root, ...Array.from(root.querySelectorAll("*"))]) {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const isLink = name === "href" || name.endsWith(":href");
      if (
        name.startsWith("on") ||
        (isLink && /^\s*javascript:/i.test(attribute.value))
      ) {
        element.removeAttribute(attribute.name);
      }
    }
  }
  root.removeAttribute("width");
  root.removeAttribute("height");
  root.setAttribute("role", "img");
  root.setAttribute("aria-label", "State diagram");
  return new XMLSerializer().serializeToString(root);
}

function stateText(node: GraphNode): string {
  const roles = [
    node.start && "start state",
    node.accepting && "accepting state",
    node.dead && "dead state",
  ].filter(Boolean);
  return `${[node.name, ...roles].join(", ")}: ${node.meaning}`;
}

function edgeText(edge: GraphEdge): string {
  return edge.epsilon
    ? `ε-transition from ${edge.source} to ${edge.target}`
    : `transition from ${edge.source} to ${edge.target} on ${edge.label}`;
}

/**
 * Text alternatives for a sanitised diagram (spec §12.2): the drawing becomes a named
 * group, each state an image named by its role and meaning, each edge an image named
 * by its symbols. The start arrow is hidden; the start state's name says it.
 */
export function labelDiagram(svg: string, graph: GraphModel): string {
  const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
  const root = doc.documentElement;
  const labels = new Map<string, string>([
    ...graph.nodes.map((node) => [node.id, stateText(node)] as const),
    ...graph.edges.map((edge) => [edge.id, edgeText(edge)] as const),
  ]);
  for (const group of Array.from(root.querySelectorAll("g[id]"))) {
    const label = labels.get(group.id);
    if (label) {
      group.setAttribute("role", "img");
      group.setAttribute("aria-label", label);
    } else if (group.id === graph.start_edge.id) {
      group.setAttribute("aria-hidden", "true");
    }
  }
  const accepting = graph.nodes.filter((n) => n.accepting).map((n) => n.name);
  const start = graph.nodes.find((n) => n.start)?.name ?? "";
  root.setAttribute("role", "group");
  root.setAttribute(
    "aria-label",
    `Automaton with ${graph.nodes.length} states, start state ${start}, accepting ${
      accepting.length > 0 ? accepting.join(", ") : "none"
    }`,
  );
  return new XMLSerializer().serializeToString(root);
}

/** The drawing's natural size in CSS pixels, from its viewBox. */
export function svgSize(svg: string): { width: number; height: number } {
  const match =
    /viewBox="([-\d.]+)[ ,]+([-\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)"/.exec(svg);
  return match
    ? { width: Number(match[3]), height: Number(match[4]) }
    : { width: 800, height: 600 };
}

type Face = { family: string; css: string };

async function asDataUrl(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(
      `could not load the font ${url} (HTTP ${response.status}).`,
    );
  }
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function familyOf(variable: string): string | null {
  const value = getComputedStyle(document.documentElement).getPropertyValue(
    variable,
  );
  const first = value
    .split(",")[0]
    ?.trim()
    .replace(/^['"]|['"]$/g, "");
  return first || null;
}

/**
 * The page's own @font-face rules for the UI and math fonts, with each file inlined.
 * An SVG drawn as an image cannot load web fonts, so they have to travel inside it.
 */
async function bundledFontFaces(): Promise<Face[]> {
  const families = new Set([
    familyOf("--font-inter"),
    familyOf("--font-noto-sans-math"),
  ]);
  const faces: Face[] = [];
  for (const sheet of Array.from(document.styleSheets)) {
    let rules: CSSRuleList;
    try {
      rules = sheet.cssRules;
    } catch {
      continue;
    }
    for (const rule of Array.from(rules)) {
      if (!(rule instanceof CSSFontFaceRule)) {
        continue;
      }
      const family = rule.style
        .getPropertyValue("font-family")
        .trim()
        .replace(/^['"]|['"]$/g, "");
      const src = /url\(["']?([^"')]+)["']?\)/.exec(
        rule.style.getPropertyValue("src"),
      )?.[1];
      if (!families.has(family) || !src) {
        continue;
      }
      // A url() in a stylesheet is relative to that stylesheet, not to the page.
      const url = new URL(src, sheet.href ?? document.baseURI).href;
      const range = rule.style.getPropertyValue("unicode-range");
      faces.push({
        family,
        css: `@font-face{font-family:'${family}';src:url(${await asDataUrl(url)}) format('woff2');${
          range ? `unicode-range:${range};` : ""
        }}`,
      });
    }
  }
  return faces;
}

/** A self-contained SVG file: light colours, the bundled fonts inlined. */
export async function standaloneSvg(svg: string): Promise<string> {
  const faces = await bundledFontFaces();
  const families = [
    ...new Set(faces.map((face) => `'${face.family}'`)),
    "sans-serif",
  ].join(",");
  const style =
    `<style>${faces.map((face) => face.css).join("")}` +
    `text{font-family:${families};fill:#0f172a}` +
    `.node ellipse,.edge path{stroke:#0f172a}.edge polygon{fill:#0f172a;stroke:#0f172a}` +
    `.dead ellipse{stroke:#64748b;stroke-dasharray:3 3}.dead text{fill:#64748b}</style>`;
  const { width, height } = svgSize(svg);
  return svg
    .replace(/<svg\b/, `<svg width="${width}" height="${height}"`)
    .replace(/(<svg\b[^>]*>)/, `$1${style}`);
}

/** The diagram as a PNG, drawn on a canvas at twice its size, on white. */
export async function renderPng(svg: string): Promise<Blob> {
  const standalone = await standaloneSvg(svg);
  const { width, height } = svgSize(svg);
  const image = new Image();
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(standalone)}`;
  await image.decode();
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(width * scale);
  canvas.height = Math.ceil(height * scale);
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("This browser cannot draw on a canvas.");
  }
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) =>
        blob ? resolve(blob) : reject(new Error("The PNG could not be made.")),
      "image/png",
    ),
  );
}

export function download(
  content: Blob | string,
  filename: string,
  type = "text/plain",
): void {
  const blob =
    typeof content === "string" ? new Blob([content], { type }) : content;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
