"use client";

import { useEffect, useRef } from "react";
import { type Geometry, pointOn } from "@/lib/sim/geometry";

/** A value the animation frames push to subscribers without re-rendering React. */
export type Signal = {
  set: (value: number) => void;
  subscribe: (listener: (value: number) => void) => () => void;
};

export function createSignal(initial = 0): Signal {
  let value = initial;
  const listeners = new Set<(value: number) => void>();
  return {
    set: (next) => {
      value = next;
      for (const listener of listeners) {
        listener(next);
      }
    },
    subscribe: (listener) => {
      listeners.add(listener);
      listener(value);
      return () => listeners.delete(listener);
    },
  };
}

/** A token travelling along the edge path with the given id, positioned by `progress`. */
export function Token({
  geometry,
  pathId,
  progress,
}: {
  geometry: Geometry;
  pathId: string;
  progress: Signal;
}) {
  const circle = useRef<SVGCircleElement>(null);

  useEffect(() => {
    const shape = geometry.edges.get(pathId);
    if (!shape) {
      return;
    }
    return progress.subscribe((t) => {
      const { x, y } = pointOn(shape, t);
      circle.current?.setAttribute("transform", `translate(${x} ${y})`);
    });
  }, [geometry, pathId, progress]);

  return <circle ref={circle} r={5} className="sim-token" />;
}
