"use client";

import { Info } from "lucide-react";
import type { AutomatonSummary } from "@/lib/api/client";
import { provenance } from "@/lib/studio/math";

/** The construction log as sentences, how the machine came about, and the assumptions. */
export function ExplanationTab({ summary }: { summary: AutomatonSummary }) {
  return (
    <div className="flex flex-col gap-6 text-sm">
      <p className="rounded-md border border-border bg-surface-2 p-3 font-medium">
        {provenance(summary.kind, summary.explanation)}
      </p>

      <section aria-labelledby="steps-title" className="flex flex-col gap-2">
        <h3 id="steps-title" className="font-semibold">
          How it was built
        </h3>
        <ol className="flex list-decimal flex-col gap-2 pl-5">
          {summary.explanation.map((entry, i) => (
            <li key={i}>
              {entry.text}{" "}
              <span className="text-xs text-subtle">
                ({entry.states} {entry.states === 1 ? "state" : "states"})
              </span>
            </li>
          ))}
        </ol>
      </section>

      {summary.warnings.length > 0 && (
        <section
          aria-labelledby="warnings-title"
          className="flex flex-col gap-2"
        >
          <h3 id="warnings-title" className="font-semibold">
            Warnings
          </h3>
          <ul className="flex flex-col gap-1 text-amber">
            {summary.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      )}

      <section
        aria-labelledby="explained-assumptions"
        className="flex flex-col gap-2"
      >
        <h3 id="explained-assumptions" className="font-semibold">
          Assumptions
        </h3>
        {summary.assumptions.length === 0 ? (
          <p className="text-muted">The description needed no assumptions.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {summary.assumptions.map((assumption) => (
              <li key={assumption.id} className="flex items-start gap-2">
                <Info
                  aria-hidden
                  className="mt-0.5 size-4 shrink-0 text-subtle"
                />
                {assumption.text}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
