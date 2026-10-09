"use client";

import {
  ChevronFirst,
  ChevronLast,
  Pause,
  Play,
  StepBack,
  StepForward,
} from "lucide-react";
import type { ReactNode } from "react";
import { useSimulator } from "@/lib/studio/context";
import { SPEEDS } from "@/lib/studio/simulator";
import { Button } from "../ui";

function Control({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <Button
      variant="ghost"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="px-2"
    >
      {children}
    </Button>
  );
}

/** Jump, step, play/pause, the scrubber over every step, and the speed. */
export function Controls({ total }: { total: number }) {
  const position = useSimulator((sim) => sim.position);
  const playing = useSimulator((sim) => sim.playing);
  const speed = useSimulator((sim) => sim.speed);
  const toStart = useSimulator((sim) => sim.toStart);
  const stepBack = useSimulator((sim) => sim.stepBack);
  const togglePlay = useSimulator((sim) => sim.togglePlay);
  const stepForward = useSimulator((sim) => sim.stepForward);
  const toEnd = useSimulator((sim) => sim.toEnd);
  const seek = useSimulator((sim) => sim.seek);
  const setSpeed = useSimulator((sim) => sim.setSpeed);
  const last = total - 1;
  const icon = "size-4";

  return (
    <div
      role="group"
      aria-label="Playback"
      className="flex flex-wrap items-center gap-x-2 gap-y-2"
    >
      <div className="flex items-center">
        <Control
          label="Jump to start (Home)"
          onClick={toStart}
          disabled={position === 0}
        >
          <ChevronFirst aria-hidden className={icon} />
        </Control>
        <Control
          label="Step back (←)"
          onClick={stepBack}
          disabled={position === 0}
        >
          <StepBack aria-hidden className={icon} />
        </Control>
        <Control
          label={playing ? "Pause (Space)" : "Play (Space)"}
          onClick={togglePlay}
        >
          {playing ? (
            <Pause aria-hidden className={icon} />
          ) : (
            <Play aria-hidden className={icon} />
          )}
        </Control>
        <Control
          label="Step forward (→)"
          onClick={stepForward}
          disabled={position === last}
        >
          <StepForward aria-hidden className={icon} />
        </Control>
        <Control
          label="Jump to end (End)"
          onClick={toEnd}
          disabled={position === last}
        >
          <ChevronLast aria-hidden className={icon} />
        </Control>
      </div>
      <input
        type="range"
        aria-label="Step"
        aria-valuetext={`Step ${position} of ${last}`}
        min={0}
        max={last}
        value={position}
        onChange={(event) => seek(Number(event.target.value))}
        className="min-w-32 flex-1 accent-(--accent)"
      />
      <span className="w-20 text-xs tabular-nums text-muted">
        {position} / {last}
      </span>
      <label className="flex items-center gap-2 text-sm">
        Speed
        <select
          value={speed}
          onChange={(event) => setSpeed(Number(event.target.value))}
          className="rounded-md border border-control-border bg-surface px-2 py-1 text-sm"
        >
          {SPEEDS.map((value) => (
            <option key={value} value={value}>
              {value}×
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
