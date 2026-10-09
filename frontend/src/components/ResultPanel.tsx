"use client";

import { TriangleAlert } from "lucide-react";
import { useStudio } from "@/lib/studio/context";
import { KIND_LABELS } from "./BuildStep";

export function ResultPanel() {
  const summary = useStudio((studio) => studio.summary);
  return (
    <section
      id="result"
      aria-labelledby="result-title"
      tabIndex={-1}
      className="flex min-h-64 flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6"
    >
      <h2 id="result-title" className="text-base font-semibold tracking-tight">
        Automaton
      </h2>
      {summary ? (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-muted">Kind</dt>
            <dd>{KIND_LABELS[summary.kind]}</dd>
            <dt className="text-muted">States</dt>
            <dd>{summary.state_count}</dd>
            <dt className="text-muted">Identifier</dt>
            <dd className="truncate font-mono text-xs leading-5" title={summary.automaton_id}>
              {summary.automaton_id}
            </dd>
          </dl>
          {summary.warnings.map((warning) => (
            <p key={warning} className="flex items-start gap-2 rounded-md bg-amber-soft p-3 text-sm text-amber">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              {warning}
            </p>
          ))}
          <section aria-labelledby="construction-title" className="flex flex-col gap-2">
            <h3 id="construction-title" className="text-sm font-semibold">
              How it was built
            </h3>
            <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm text-muted">
              {summary.explanation.map((entry, i) => (
                <li key={i}>
                  <span className="text-text">{entry.text}</span>{" "}
                  <span className="text-xs">({entry.states} states)</span>
                </li>
              ))}
            </ol>
          </section>
        </>
      ) : (
        <p className="text-sm text-muted">
          Describe a language and confirm the reading; the verified automaton appears here.
        </p>
      )}
    </section>
  );
}
