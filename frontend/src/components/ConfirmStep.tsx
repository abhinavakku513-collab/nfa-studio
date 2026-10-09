"use client";

import { Info, LoaderCircle } from "lucide-react";
import type { KeyboardEvent } from "react";
import type { Assumption } from "@/lib/api/client";
import { useStudio } from "@/lib/studio/context";
import { ErrorNotice } from "./ErrorNotice";
import { Reading } from "./Reading";
import { Button, Kbd, StepCard, Switch } from "./ui";

const TOPICS: Record<string, string> = {
  count_exact_or_at_least: "a count",
  overlap: "overlapping occurrences",
  grouping: "how the conditions group",
  alphabet: "the alphabet",
};

function Assumptions({ assumptions }: { assumptions: Assumption[] }) {
  const rejected = useStudio((studio) => studio.rejected);
  const setAccepted = useStudio((studio) => studio.setAccepted);
  const openManual = useStudio((studio) => studio.openManual);
  if (assumptions.length === 0) {
    return null;
  }
  return (
    <section
      aria-labelledby="assumptions-title"
      className="flex flex-col gap-2"
    >
      <h3 id="assumptions-title" className="text-sm font-semibold">
        Assumptions
      </h3>
      <ul className="flex flex-col gap-2">
        {assumptions.map((assumption) => (
          <li
            key={assumption.id}
            className="flex items-start gap-3 rounded-md bg-surface-2 px-3 py-2 text-sm"
          >
            {assumption.editable ? (
              <Switch
                checked={!rejected.includes(assumption.id)}
                onChange={(checked) => setAccepted(assumption.id, checked)}
                label={`Accept: ${assumption.text}`}
              />
            ) : (
              <Info
                aria-hidden
                className="mt-0.5 size-4 shrink-0 text-subtle"
              />
            )}
            <span className="flex-1">
              {assumption.text}
              {!assumption.editable && (
                <span className="ml-2 text-xs text-subtle">always true</span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {rejected.length > 0 && (
        <p className="text-sm text-amber">
          Building waits while an assumption is off. Change the reading so it no
          longer applies,{" "}
          <button
            type="button"
            onClick={openManual}
            className="font-medium underline underline-offset-2"
          >
            edit the IR directly
          </button>
          , or turn the assumption back on.
        </p>
      )}
    </section>
  );
}

function QuestionCard() {
  const question = useStudio((studio) => studio.question);
  const busy = useStudio((studio) => studio.busy);
  const answer = useStudio((studio) => studio.answer);
  if (!question) {
    return null;
  }
  return (
    <div
      role="group"
      aria-labelledby="question-text"
      className="flex flex-col gap-3 rounded-md border border-amber/50 bg-amber-soft p-4"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-amber">
        Question {question.id.replace("Q", "")} ·{" "}
        {TOPICS[question.topic] ?? question.topic}
      </p>
      <p id="question-text" className="text-sm font-medium">
        {question.text}
      </p>
      <div className="flex flex-wrap gap-2">
        {question.options.map((option) => (
          <Button
            key={option.id}
            variant={option.id === "edit" ? "ghost" : "secondary"}
            disabled={busy !== null}
            onClick={() => void answer(option.id)}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

function ManualIrForm() {
  const manualText = useStudio((studio) => studio.manualText);
  const missing = useStudio((studio) => studio.missing);
  const busy = useStudio((studio) => studio.busy);
  const setManualText = useStudio((studio) => studio.setManualText);
  const buildManual = useStudio((studio) => studio.buildManual);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (
      event.key === "Enter" &&
      (event.ctrlKey || event.metaKey) &&
      busy === null
    ) {
      event.preventDefault();
      void buildManual();
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {missing.length > 0 && (
        <p className="text-sm text-amber">
          More than two questions would be needed (
          {missing.map((topic) => TOPICS[topic] ?? topic).join(", ")}), so the
          reading so far is shown as IR. Fill in what is missing, then build.
        </p>
      )}
      <label htmlFor="manual-ir" className="text-sm font-medium">
        Specification (LSIR JSON)
      </label>
      <textarea
        id="manual-ir"
        value={manualText}
        rows={14}
        spellCheck={false}
        onChange={(event) => setManualText(event.target.value)}
        onKeyDown={onKeyDown}
        aria-describedby="manual-ir-hint"
        className="rounded-md border border-control-border bg-surface px-3 py-2 font-mono text-xs leading-5"
      />
      <p id="manual-ir-hint" className="text-xs text-subtle">
        <Kbd>Ctrl</Kbd> + <Kbd>Enter</Kbd> builds from this IR. The server
        checks it against the schema.
      </p>
      <div>
        <Button
          variant="primary"
          onClick={() => void buildManual()}
          disabled={busy !== null}
        >
          {busy === "build" && (
            <LoaderCircle
              aria-hidden
              className="size-4 animate-spin motion-reduce:animate-none"
            />
          )}
          Build from this IR
        </Button>
      </div>
    </div>
  );
}

export function ConfirmStep() {
  const stage = useStudio((studio) => studio.stage);
  const ir = useStudio((studio) => studio.ir);
  const partialIr = useStudio((studio) => studio.partialIr);
  const problem = useStudio((studio) =>
    studio.problemStep === "confirm" ? studio.problem : null,
  );
  const dismissProblem = useStudio((studio) => studio.dismissProblem);
  const editIr = useStudio((studio) => studio.editIr);
  const openManual = useStudio((studio) => studio.openManual);

  if (stage === "describe") {
    return (
      <StepCard step={2} title="Confirm">
        <p className="text-sm text-muted">
          The reading of your description appears here for you to check.
        </p>
      </StepCard>
    );
  }

  return (
    <StepCard
      step={2}
      title="Confirm"
      done={stage === "built"}
      aside={
        stage !== "editing" && ir ? (
          <Button variant="ghost" onClick={openManual} className="py-1 text-xs">
            Edit as IR
          </Button>
        ) : null
      }
    >
      {stage === "editing" ? (
        <ManualIrForm />
      ) : stage === "asking" ? (
        <>
          {partialIr && <Reading ir={partialIr} onEdit={editIr} readOnly />}
          <QuestionCard />
        </>
      ) : (
        ir && (
          <>
            <Reading ir={ir} onEdit={editIr} />
            <p className="text-xs text-subtle">
              Select a highlighted value to change it.
            </p>
            <Assumptions assumptions={ir.assumptions} />
          </>
        )
      )}
      {problem && <ErrorNotice problem={problem} onDismiss={dismissProblem} />}
    </StepCard>
  );
}
