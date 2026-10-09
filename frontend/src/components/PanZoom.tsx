"use client";

import { Maximize, Minus, Plus } from "lucide-react";
import {
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Button } from "./ui";

type Viewport = { x: number; y: number; k: number };

const FIT: Viewport = { x: 0, y: 0, k: 1 };
const MIN_SCALE = 0.25;
const MAX_SCALE = 4;
const STEP = 1.25;
const PAN = 48;

/** Zoom by `factor` about the point (cx, cy), which stays where it is on screen. */
function zoomAt(
  view: Viewport,
  cx: number,
  cy: number,
  factor: number,
): Viewport {
  const k = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.k * factor));
  const ratio = k / view.k;
  return { k, x: cx - (cx - view.x) * ratio, y: cy - (cy - view.y) * ratio };
}

/**
 * The inlined diagram with pan and zoom: wheel or buttons to zoom, drag to pan, and from
 * the keyboard + / − to zoom, arrow keys to pan and 0 to fit. `svg` must already be
 * sanitised. Hovering a state reports its name; `highlight` outlines one state.
 * `onSvg` receives the inlined <svg> element, `overlay` is drawn above the diagram.
 */
export function PanZoom({
  svg,
  label,
  highlight,
  onHover,
  onSvg,
  overlay,
}: {
  svg: string;
  label: string;
  highlight: string | null;
  onHover: (state: string | null) => void;
  onSvg?: (element: SVGSVGElement | null) => void;
  overlay?: ReactNode;
}) {
  const [view, setView] = useState<Viewport>(FIT);
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    startX: number;
    startY: number;
    from: Viewport;
  } | null>(null);

  // React's wheel listener is passive, and the page must not scroll while zooming.
  useEffect(() => {
    const element = viewport.current;
    if (!element) {
      return;
    }
    function onWheel(event: WheelEvent): void {
      event.preventDefault();
      const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * 0.0015);
      setView((current) =>
        zoomAt(
          current,
          event.clientX - box.left,
          event.clientY - box.top,
          factor,
        ),
      );
    }
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, []);

  useLayoutEffect(() => {
    onSvg?.(content.current?.querySelector("svg") ?? null);
    return () => onSvg?.(null);
  }, [svg, onSvg]);

  useEffect(() => {
    const root = content.current;
    if (!root) {
      return;
    }
    for (const element of Array.from(
      root.querySelectorAll(".is-highlighted"),
    )) {
      element.classList.remove("is-highlighted");
    }
    if (highlight) {
      root
        .querySelector(`[id="s-${highlight}"]`)
        ?.classList.add("is-highlighted");
    }
  }, [highlight, svg]);

  function zoomCentre(factor: number): void {
    const box = viewport.current?.getBoundingClientRect();
    setView((current) =>
      zoomAt(current, (box?.width ?? 0) / 2, (box?.height ?? 0) / 2, factor),
    );
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const pans: Record<string, [number, number]> = {
      ArrowLeft: [PAN, 0],
      ArrowRight: [-PAN, 0],
      ArrowUp: [0, PAN],
      ArrowDown: [0, -PAN],
    };
    if (event.key === "+" || event.key === "=") {
      zoomCentre(STEP);
    } else if (event.key === "-") {
      zoomCentre(1 / STEP);
    } else if (event.key === "0") {
      setView(FIT);
    } else if (event.key in pans) {
      const [dx, dy] = pans[event.key];
      setView((current) => ({
        ...current,
        x: current.x + dx,
        y: current.y + dy,
      }));
    } else {
      return;
    }
    event.preventDefault();
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>): void {
    if (event.button !== 0) {
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { startX: event.clientX, startY: event.clientY, from: view };
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>): void {
    const start = drag.current;
    if (start) {
      setView({
        ...start.from,
        x: start.from.x + event.clientX - start.startX,
        y: start.from.y + event.clientY - start.startY,
      });
    }
  }

  function onPointerOver(event: PointerEvent<HTMLDivElement>): void {
    const state =
      event.target instanceof Element ? event.target.closest("g.state") : null;
    onHover(state ? state.id.replace(/^s-/, "") : null);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          aria-label="Zoom out"
          onClick={() => zoomCentre(1 / STEP)}
          className="px-2"
        >
          <Minus aria-hidden className="size-4" />
        </Button>
        <span
          className="w-12 text-center text-xs tabular-nums text-muted"
          aria-live="polite"
        >
          {Math.round(view.k * 100)}%
        </span>
        <Button
          variant="ghost"
          aria-label="Zoom in"
          onClick={() => zoomCentre(STEP)}
          className="px-2"
        >
          <Plus aria-hidden className="size-4" />
        </Button>
        <Button
          variant="ghost"
          onClick={() => setView(FIT)}
          className="px-2 text-xs"
        >
          <Maximize aria-hidden className="size-4" />
          Fit
        </Button>
      </div>
      <div
        ref={viewport}
        role="group"
        aria-label={`${label}. Use + and − to zoom, the arrow keys to pan and 0 to fit.`}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
        onPointerOver={onPointerOver}
        onPointerLeave={() => onHover(null)}
        className="relative h-[28rem] cursor-grab touch-none overflow-hidden rounded-md border border-border bg-bg active:cursor-grabbing"
      >
        <div
          ref={content}
          className="diagram absolute inset-0 origin-top-left p-4"
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`,
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
        {overlay}
      </div>
    </div>
  );
}
