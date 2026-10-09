"use client";

import clsx from "clsx";
import { Circle, CircleCheck, CircleX, LoaderCircle, Shield, ShieldAlert, ShieldCheck } from "lucide-react";
import type { AutomatonSummary, Verification } from "@/lib/api/client";
import { useStudio } from "@/lib/studio/context";
import { ErrorNotice } from "./ErrorNotice";
import { Button, StepCard } from "./ui";

export const KIND_LABELS: Record<AutomatonSummary["kind"], string> = {
  enfa: "ε-NFA",
  nfa: "NFA",
  dfa: "DFA",
};

type StepState = "waiting" | "running" | "done" | "failed";

const STEP_ICONS = {
  waiting: Circle,
  running: LoaderCircle,
  done: CircleCheck,
  failed: CircleX,
} as const;

function ProgressStep({ label, state, note }: { label: string; state: StepState; note?: string }) {
  const Icon = STEP_ICONS[state];
  return (
    <li className="flex items-center gap-2 text-sm">
      <Icon
        aria-hidden
        className={clsx(
          "size-4 shrink-0",
          state === "running" && "animate-spin text-accent motion-reduce:animate-none",
          state === "done" && "text-accent",
          state === "failed" && "text-danger",
          state === "waiting" && "text-subtle",
        )}
      />
      <span className={clsx("font-medium", state === "waiting" && "text-subtle")}>{label}</span>
      {note && <span className="text-xs text-muted">{note}</span>}
      <span className="sr-only">{state}</span>
    </li>
  );
}

const BADGES = {
  green: { Icon: ShieldCheck, tone: "border-accent/50 bg-accent-soft text-accent" },
  amber: { Icon: ShieldAlert, tone: "border-amber/50 bg-amber-soft text-amber" },
  grey: { Icon: Shield, tone: "border-border-strong bg-neutral-soft text-muted" },
} as const;

/** spec §8.2: grey = V0 only, amber = V1, green = V2; always an icon and words, never colour alone. */
export function VerificationBadge({ verification }: { verification: Verification }) {
  const { Icon, tone } = BADGES[verification.badge];
  const strongest = verification.checks.find((check) => check.level === verification.level);
  return (
    <div className={clsx("flex flex-col gap-2 rounded-md border p-4", tone)}>
      <p className="flex items-center gap-2 text-sm font-semibold">
        <Icon aria-hidden className="size-5 shrink-0" />
        <span>
          {verification.level} · {strongest?.evidence ?? "Verified"}
        </span>
      </p>
      <ul className="flex flex-col gap-1 text-xs text-text">
        {verification.checks.map((check) => (
          <li key={check.level}>
            <span className="font-mono">{check.level}</span> {check.evidence}
          </li>
        ))}
      </ul>
      {verification.notes.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-muted">
          {verification.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function BuildStep() {
  const stage = useStudio((studio) => studio.stage);
  const busy = useStudio((studio) => studio.busy);
  const ir = useStudio((studio) => studio.ir);
  const rejected = useStudio((studio) => studio.rejected);
  const summary = useStudio((studio) => studio.summary);
  const problem = useStudio((studio) => (studio.problemStep === "build" ? studio.problem : null));
  const build = useStudio((studio) => studio.build);

  const building = busy === "build";
  const failedVerify = problem?.code === "E_VERIFY_FAILED";
  const compiled: StepState = building ? "running" : summary || failedVerify ? "done" : problem ? "failed" : "waiting";
  const verified: StepState = building ? "running" : summary ? "done" : failedVerify ? "failed" : "waiting";
  const canBuild = stage === "confirming" && ir !== null && busy === null && rejected.length === 0;

  const status = building
    ? "Compiling and verifying"
    : summary
      ? `Built a ${KIND_LABELS[summary.kind]} with ${summary.state_count} states; reached ${summary.verification.level}`
      : problem
        ? "The build failed"
        : "";

  return (
    <StepCard step={3} title="Build" done={summary !== null}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <ol aria-label="Build progress" className="flex flex-wrap items-center gap-4">
          <ProgressStep
            label="Compiled"
            state={compiled}
            note={summary ? `${summary.state_count} states · ${KIND_LABELS[summary.kind]}` : undefined}
          />
          <li aria-hidden className="h-px w-6 bg-border-strong" />
          <ProgressStep label="Verified" state={verified} />
        </ol>
        {stage !== "editing" && (
          <Button variant="primary" onClick={() => void build()} disabled={!canBuild}>
            Build and verify
          </Button>
        )}
      </div>
      <p aria-live="polite" className="sr-only">
        {status}
      </p>
      {summary && <VerificationBadge verification={summary.verification} />}
      {problem && <ErrorNotice problem={problem} />}
    </StepCard>
  );
}
