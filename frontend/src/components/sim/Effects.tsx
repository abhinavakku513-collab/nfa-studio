"use client";

import type { StateShape } from "@/lib/sim/geometry";

/**
 * A soft ring that spreads from a state reached by ε (`ripple`), or the ring pulse on an
 * accepting state at the verdict (`pulse`). It removes itself when its CSS animation ends.
 */
export function Ripple({
  shape,
  variant,
  duration,
  onEnd,
}: {
  shape: StateShape;
  variant: "ripple" | "pulse";
  duration: number;
  onEnd: () => void;
}) {
  return (
    <circle
      cx={shape.cx}
      cy={shape.cy}
      r={shape.r + 2}
      className={variant === "pulse" ? "sim-pulse" : "sim-ripple"}
      style={{ animationDuration: `${duration}ms` }}
      onAnimationEnd={onEnd}
    />
  );
}

/** The brief red outline on a state that dropped out of the active set (200 ms). */
export function Dropout({
  shape,
  onEnd,
}: {
  shape: StateShape;
  onEnd: () => void;
}) {
  return (
    <circle
      cx={shape.cx}
      cy={shape.cy}
      r={shape.r + 1}
      className="sim-dropout"
      onAnimationEnd={onEnd}
    />
  );
}
