"use client";

import { CircleAlert, X } from "lucide-react";
import type { IRDocument, Problem } from "@/lib/api/client";
import { useStudio } from "@/lib/studio/context";
import { Button } from "./ui";

const TITLES: Record<string, string> = {
  E_SCHEMA_INVALID: "The specification is not valid",
  E_ALPHABET_MISSING: "No alphabet could be found",
  E_UNSUPPORTED_NONREGULAR: "This language is not regular",
  E_UNSUPPORTED_FEATURE: "This description cannot be read",
  E_SYMBOL_NOT_IN_ALPHABET: "A symbol is not in the alphabet",
  E_INPUT_TOO_LONG: "The input is too long",
  E_STATE_LIMIT: "The automaton would be too large",
  E_TIMEOUT: "This took too long",
  E_VERIFY_FAILED: "Verification failed",
  E_AUTOMATON_NOT_FOUND: "The automaton has expired",
  E_SESSION_NOT_FOUND: "The question has expired",
  E_RATE_LIMITED: "Too many requests",
  E_NETWORK: "The server cannot be reached",
};

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function alternativeOf(detail: Record<string, unknown>): { text: string; ir: IRDocument | null } | null {
  const alternative = detail.alternative;
  if (typeof alternative !== "object" || alternative === null) {
    return null;
  }
  const { text, ir } = alternative as { text?: unknown; ir?: unknown };
  if (typeof text !== "string") {
    return null;
  }
  return { text, ir: typeof ir === "object" && ir !== null ? (ir as IRDocument) : null };
}

/** An API error with its reason and next action, plus whatever help its detail carries. */
export function ErrorNotice({ problem }: { problem: Problem }) {
  const setText = useStudio((studio) => studio.setText);
  const loadIr = useStudio((studio) => studio.loadIr);
  const dismiss = useStudio((studio) => studio.dismissProblem);

  const detail = problem.detail;
  const errors = strings(detail.errors);
  const examples = strings(detail.examples);
  const alternative = alternativeOf(detail);
  const counterexample = typeof detail.counterexample === "string" ? detail.counterexample : null;

  return (
    <div role="alert" className="flex gap-3 rounded-md border border-danger/40 bg-danger-soft p-4 text-sm">
      <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="font-semibold text-danger">
          {TITLES[problem.code] ?? "Something went wrong"}{" "}
          <span className="font-mono text-xs font-normal text-muted">{problem.code}</span>
        </p>
        <p className="text-text">{problem.message}</p>
        {errors.length > 0 && (
          <ul className="list-disc pl-5 font-mono text-xs text-muted">
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        )}
        {counterexample !== null && (
          <p className="text-muted">
            Counterexample:{" "}
            <code className="rounded bg-surface px-1 font-mono text-text">{counterexample || "ε"}</code>
          </p>
        )}
        {alternative?.ir && (
          <div>
            <Button variant="secondary" onClick={() => loadIr(alternative.ir as IRDocument)}>
              Use the regular alternative
            </Button>
          </div>
        )}
        {examples.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {examples.map((example) => (
              <Button key={example} variant="secondary" onClick={() => setText(example)} className="py-1 text-xs">
                {example}
              </Button>
            ))}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss this message"
        className="size-7 shrink-0 rounded-md text-muted hover:bg-surface hover:text-text"
      >
        <X aria-hidden className="mx-auto size-4" />
      </button>
    </div>
  );
}
