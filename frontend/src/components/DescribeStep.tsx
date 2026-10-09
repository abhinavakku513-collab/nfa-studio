"use client";

import { LoaderCircle } from "lucide-react";
import type { KeyboardEvent } from "react";
import { formatSymbols, parseSymbols } from "@/lib/studio/ir";
import { useStudio } from "@/lib/studio/context";
import { EditableChip } from "./EditableChip";
import { ErrorNotice } from "./ErrorNotice";
import { Button, Kbd, StepCard } from "./ui";

// General examples, written for this page rather than taken from the benchmark.
export const EXAMPLES = [
  "strings over {a,b} with an even number of a's",
  "binary strings that contain 101",
  "strings over {a,b,c} that start with ab and end with c",
  "binary strings with no three consecutive 0s",
  "strings over {a,b} whose second symbol from the end is b",
] as const;

const SOURCE_LABELS = { user: "given", inferred: "inferred", default: "default" } as const;

function AlphabetChip() {
  const ir = useStudio((studio) => studio.ir);
  const override = useStudio((studio) => studio.alphabetOverride);
  const setAlphabet = useStudio((studio) => studio.setAlphabet);

  const symbols = ir?.alphabet.symbols ?? override;
  const source = ir ? SOURCE_LABELS[ir.alphabet.source] : override ? "given" : null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted">Alphabet</span>
      <EditableChip
        label="Alphabet"
        value={symbols ? symbols.join(", ") : ""}
        shown={symbols ? formatSymbols(symbols) : "from the description"}
        mono={Boolean(symbols)}
        onCommit={(text) => setAlphabet(parseSymbols(text))}
      />
      {source && <span className="text-xs text-subtle">{source}</span>}
    </div>
  );
}

export function DescribeStep() {
  const text = useStudio((studio) => studio.text);
  const busy = useStudio((studio) => studio.busy);
  const stage = useStudio((studio) => studio.stage);
  const problem = useStudio((studio) => (studio.problemStep === "describe" ? studio.problem : null));
  const setText = useStudio((studio) => studio.setText);
  const interpret = useStudio((studio) => studio.interpret);

  const reading = busy === "interpret";
  const canRead = text.trim().length > 0 && busy === null;

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && canRead) {
      event.preventDefault();
      void interpret();
    }
  }

  return (
    <StepCard step={1} title="Describe" done={stage !== "describe"}>
      <div className="flex flex-col gap-2">
        <label htmlFor="description" className="text-sm font-medium">
          Describe a set of strings in plain English
        </label>
        <textarea
          id="description"
          value={text}
          rows={3}
          maxLength={500}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby="description-hint"
          placeholder="e.g. strings over {a,b} that contain aba but do not end with b"
          className="resize-y rounded-md border border-border-strong bg-surface px-3 py-2 text-sm placeholder:text-subtle"
        />
        <p id="description-hint" className="text-xs text-subtle">
          <Kbd>Ctrl</Kbd> + <Kbd>Enter</Kbd> reads the description.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-muted">Examples</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setText(example)}
              className="rounded-full border border-border-strong px-3 py-1 text-xs text-muted hover:border-accent hover:text-text"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <AlphabetChip />
        <Button variant="primary" onClick={() => void interpret()} disabled={!canRead}>
          {reading && <LoaderCircle aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />}
          {reading ? "Reading…" : "Read description"}
        </Button>
      </div>

      {problem && <ErrorNotice problem={problem} />}
    </StepCard>
  );
}
