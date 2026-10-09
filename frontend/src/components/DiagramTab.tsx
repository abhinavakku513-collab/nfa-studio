"use client";

import clsx from "clsx";
import { LoaderCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { GraphNode } from "@/lib/api/client";
import { useExplore } from "@/lib/studio/context";
import { viewKey } from "@/lib/studio/explore";
import { download, renderPng, sanitizeSvg, standaloneSvg } from "@/lib/svg";
import { ErrorNotice } from "./ErrorNotice";
import { PanZoom } from "./PanZoom";
import { ExportButtons, ViewToggles } from "./ViewToggles";

function Legend({
  nodes,
  active,
  onActive,
}: {
  nodes: readonly GraphNode[];
  active: string | null;
  onActive: (state: string | null) => void;
}) {
  return (
    <section aria-labelledby="legend-title" className="flex flex-col gap-2">
      <h3 id="legend-title" className="text-sm font-semibold">
        States and their meanings
      </h3>
      <ul className="flex flex-col gap-1">
        {nodes.map((node) => (
          <li
            key={node.id}
            tabIndex={0}
            aria-current={active === node.name ? "true" : undefined}
            onMouseEnter={() => onActive(node.name)}
            onMouseLeave={() => onActive(null)}
            onFocus={() => onActive(node.name)}
            onBlur={() => onActive(null)}
            className={clsx(
              "flex items-baseline gap-3 rounded-md px-2 py-1 text-sm",
              active === node.name ? "bg-accent-soft" : "hover:bg-surface-2",
            )}
          >
            <span className="w-10 shrink-0 font-mono">{node.name}</span>
            <span className="flex-1">
              {node.meaning}
              <span className="ml-2 text-xs text-subtle">
                {[
                  node.start && "start",
                  node.accepting && "accepting",
                  node.dead && "dead",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The Graphviz diagram, inlined and sanitised, with pan, zoom, legend and exports. */
export function DiagramTab({
  id,
  hasEpsilon,
}: {
  id: string;
  hasEpsilon: boolean;
}) {
  const view = useExplore((explore) => explore.view);
  const key = viewKey(id, view);
  const svgEntry = useExplore((explore) => explore.svgs[key]);
  const graphEntry = useExplore((explore) => explore.graphs[key]);
  const loadSvg = useExplore((explore) => explore.loadSvg);
  const loadGraph = useExplore((explore) => explore.loadGraph);
  const dotText = useExplore((explore) => explore.dotText);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    void loadSvg(id);
    void loadGraph(id);
  }, [id, key, loadSvg, loadGraph]);

  const svg = useMemo(() => {
    if (svgEntry?.status !== "ready") {
      return null;
    }
    try {
      return { markup: sanitizeSvg(svgEntry.data), error: null };
    } catch (error) {
      return { markup: null, error: (error as Error).message };
    }
  }, [svgEntry]);

  const nodes = graphEntry?.status === "ready" ? graphEntry.data.nodes : [];
  const hoveredNode = nodes.find((node) => node.name === hovered);
  const name = `nfa-${id.replace(/^sha256:/, "").slice(0, 12)}`;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <ViewToggles hasEpsilon={hasEpsilon} />
        {svg?.markup && (
          <ExportButtons
            options={[
              {
                label: "SVG",
                run: async () =>
                  download(
                    await standaloneSvg(svg.markup),
                    `${name}.svg`,
                    "image/svg+xml",
                  ),
              },
              {
                label: "PNG",
                run: async () =>
                  download(await renderPng(svg.markup), `${name}.png`),
              },
              {
                label: "DOT",
                run: async () =>
                  download(
                    await dotText(id),
                    `${name}.dot`,
                    "text/vnd.graphviz",
                  ),
              },
            ]}
          />
        )}
      </div>

      {svgEntry?.status === "failed" ? (
        <ErrorNotice problem={svgEntry.problem} />
      ) : svg?.error ? (
        <p role="alert" className="text-sm text-danger">
          {svg.error} Try the Table tab instead.
        </p>
      ) : svg?.markup ? (
        <>
          <PanZoom
            svg={svg.markup}
            label="State diagram"
            highlight={hovered}
            onHover={setHovered}
          />
          <p aria-live="polite" className="min-h-5 text-sm text-muted">
            {hoveredNode ? (
              <>
                <span className="font-mono text-text">{hoveredNode.name}</span>:{" "}
                {hoveredNode.meaning}
              </>
            ) : (
              "Point at a state, or focus one in the list below, to see what it means."
            )}
          </p>
        </>
      ) : (
        <p className="flex h-[28rem] items-center justify-center gap-2 rounded-md border border-border text-sm text-muted">
          <LoaderCircle
            aria-hidden
            className="size-4 animate-spin motion-reduce:animate-none"
          />
          Laying out the diagram…
        </p>
      )}

      {graphEntry?.status === "ready" && (
        <>
          {graphEntry.data.hidden_dead_states.length > 0 && (
            <p className="text-xs text-subtle">
              Hidden dead states:{" "}
              {graphEntry.data.hidden_dead_states.join(", ")}. Turn on “Show
              dead states” to include them.
            </p>
          )}
          <Legend nodes={nodes} active={hovered} onActive={setHovered} />
        </>
      )}
    </div>
  );
}
