"use client";

import { Download, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { ProblemError } from "@/lib/api/client";
import { useExplore } from "@/lib/studio/context";
import { Button, Switch } from "./ui";

/** "Show dead states" and, for machines with ε edges, "ε-free version" (spec §10). */
export function ViewToggles({ hasEpsilon }: { hasEpsilon: boolean }) {
  const view = useExplore((explore) => explore.view);
  const setView = useExplore((explore) => explore.setView);
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
      <label className="flex items-center gap-2">
        <Switch
          checked={view.showDead}
          onChange={(showDead) => setView({ showDead })}
          label="Show dead states"
        />
        Show dead states
      </label>
      {hasEpsilon && (
        <label className="flex items-center gap-2">
          <Switch
            checked={view.epsFree}
            onChange={(epsFree) => setView({ epsFree })}
            label="ε-free version"
          />
          ε-free version
        </label>
      )}
    </div>
  );
}

export type ExportOption = { label: string; run: () => Promise<void> };

/** A row of export buttons; a failed export says why next to them. */
export function ExportButtons({
  options,
}: {
  options: readonly ExportOption[];
}) {
  const [running, setRunning] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function start(option: ExportOption): Promise<void> {
    setRunning(option.label);
    setFailure(null);
    try {
      await option.run();
    } catch (error) {
      const reason =
        error instanceof ProblemError
          ? error.problem.message
          : (error as Error).message;
      setFailure(
        `${option.label} export failed: ${reason.replace(/\.?$/, ".")} Try again, or choose another format.`,
      );
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div
        role="group"
        aria-label="Export"
        className="flex flex-wrap items-center gap-1"
      >
        <span className="mr-1 text-xs text-muted">Export</span>
        {options.map((option) => (
          <Button
            key={option.label}
            variant="secondary"
            onClick={() => void start(option)}
            disabled={running !== null}
            className="px-2 py-1 text-xs"
          >
            {running === option.label ? (
              <LoaderCircle
                aria-hidden
                className="size-3.5 animate-spin motion-reduce:animate-none"
              />
            ) : (
              <Download aria-hidden className="size-3.5" />
            )}
            {option.label}
          </Button>
        ))}
      </div>
      {failure && (
        <p role="status" className="text-xs text-danger">
          {failure}
        </p>
      )}
    </div>
  );
}
