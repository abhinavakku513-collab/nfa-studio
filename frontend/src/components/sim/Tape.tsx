"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { DURATIONS } from "@/lib/sim/timeline";

const CELL = 32;
// Cells drawn either side of the head; a 10 000-symbol word stays a few dozen nodes.
const WINDOW = 60;

/**
 * The input tape: slot 0 is the left end ⊢, slot i holds symbol i. The head outlines
 * the symbol being read and slides over in the read phase; read cells dim. The strip
 * scrolls only once the head passes the middle, by a width measured on resize.
 */
export function Tape({
  word,
  head,
  speed,
}: {
  word: string;
  head: number;
  speed: number;
}) {
  const symbols = useMemo(() => Array.from(word), [word]);
  const viewport = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = viewport.current;
    if (!element || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(([entry]) =>
      setWidth(entry.contentRect.width),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const offset = Math.max(0, (head + 0.5) * CELL - width / 2);
  const first = Math.max(1, head - WINDOW);
  const last = Math.min(symbols.length, head + WINDOW);
  const slide = { transitionDuration: `${DURATIONS.read / speed}ms` };

  return (
    <div
      ref={viewport}
      tabIndex={0}
      role="group"
      aria-label={`Input tape, ${head} of ${symbols.length} symbols read. Space plays or pauses, the arrow keys step, Home and End jump.`}
      className="relative h-16 overflow-hidden rounded-md border border-border bg-surface-2"
    >
      <div
        aria-hidden
        className="absolute inset-y-0 left-2 transition-transform ease-in-out motion-reduce:transition-none"
        style={{ transform: `translateX(${-offset}px)`, ...slide }}
      >
        <span
          className="absolute top-4 flex h-8 w-8 items-center justify-center font-mono text-subtle"
          style={{ left: 0 }}
        >
          ⊢
        </span>
        {symbols.length === 0 && (
          <span
            className="absolute top-4 flex h-8 items-center whitespace-nowrap pl-2 text-sm text-muted"
            style={{ left: CELL }}
          >
            ε, the empty word
          </span>
        )}
        {Array.from({ length: Math.max(0, last - first + 1) }, (_, i) => {
          const slot = first + i;
          return (
            <span
              key={slot}
              className={clsx(
                "absolute top-4 flex h-8 w-8 items-center justify-center border-y border-r border-border-strong font-mono text-base transition-colors duration-200 motion-reduce:transition-none",
                slot === 1 && "border-l",
                // Read cells dim by colour, not opacity, so they keep 4.5:1.
                slot <= head ? "bg-surface-2 text-muted" : "bg-surface",
              )}
              style={{ left: slot * CELL }}
            >
              {symbols[slot - 1]}
            </span>
          );
        })}
        <span
          className="absolute top-2 h-12 w-8 rounded-md border-2 border-accent transition-[left] ease-in-out motion-reduce:transition-none"
          style={{ left: head * CELL, ...slide }}
        />
      </div>
    </div>
  );
}
