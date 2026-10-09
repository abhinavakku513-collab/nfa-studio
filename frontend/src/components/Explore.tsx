"use client";

import { TriangleAlert } from "lucide-react";
import { useStudio } from "@/lib/studio/context";
import { KIND_LABELS } from "./BuildStep";
import { DiagramTab } from "./DiagramTab";
import { ExplanationTab } from "./ExplanationTab";
import { FormalTab } from "./FormalTab";
import { TableTab } from "./TableTab";
import { Tabs } from "./Tabs";

/** The right column of spec §12.1: Diagram · Table · Formal definition · Explanation. */
export function Explore() {
  const summary = useStudio((studio) => studio.summary);
  return (
    <section
      id="result"
      aria-labelledby="result-title"
      tabIndex={-1}
      className="flex min-h-64 min-w-0 flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6"
    >
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2
          id="result-title"
          className="text-base font-semibold tracking-tight"
        >
          Automaton
        </h2>
        {summary && (
          <p className="flex min-w-0 flex-wrap items-baseline gap-x-3 text-sm text-muted">
            <span>
              {KIND_LABELS[summary.kind]} · {summary.state_count} states
            </span>
            <span
              className="truncate font-mono text-xs"
              title={summary.automaton_id}
            >
              {summary.automaton_id}
            </span>
          </p>
        )}
      </header>
      {summary ? (
        <>
          {summary.warnings.map((warning) => (
            <p
              key={warning}
              className="flex items-start gap-2 rounded-md bg-amber-soft p-3 text-sm text-amber"
            >
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              {warning}
            </p>
          ))}
          <Tabs
            key={summary.automaton_id}
            label="Views of the automaton"
            tabs={[
              {
                id: "diagram",
                title: "Diagram",
                content: (
                  <DiagramTab
                    id={summary.automaton_id}
                    hasEpsilon={summary.kind === "enfa"}
                  />
                ),
              },
              {
                id: "table",
                title: "Table",
                content: (
                  <TableTab
                    id={summary.automaton_id}
                    hasEpsilon={summary.kind === "enfa"}
                  />
                ),
              },
              {
                id: "formal",
                title: "Formal definition",
                content: <FormalTab id={summary.automaton_id} />,
              },
              {
                id: "explanation",
                title: "Explanation",
                content: <ExplanationTab summary={summary} />,
              },
            ]}
          />
        </>
      ) : (
        <p className="text-sm text-muted">
          Describe a language and confirm the reading; the verified automaton
          appears here.
        </p>
      )}
    </section>
  );
}
