"use client";

import clsx from "clsx";
import { type KeyboardEvent, useState } from "react";

const CHIP =
  "inline-flex min-h-7 items-center rounded-md border px-2 py-0.5 align-baseline text-sm";

/**
 * A value inside the plain-English reading. Enter or a click opens it for editing;
 * Enter or leaving the field commits, Escape cancels. With `options` it is a select.
 */
export function EditableChip({
  label,
  value,
  shown,
  onCommit,
  options,
  mono = false,
  readOnly = false,
}: {
  label: string;
  value: string;
  shown?: string;
  onCommit: (value: string) => void;
  options?: readonly { value: string; label: string }[];
  mono?: boolean;
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const text =
    shown ?? options?.find((option) => option.value === value)?.label ?? value;
  const face = clsx(
    CHIP,
    mono && "font-mono",
    "border-accent/40 bg-accent-soft text-text",
  );

  if (readOnly) {
    return (
      <span
        className={clsx(
          CHIP,
          mono && "font-mono",
          "border-border bg-surface-2",
        )}
      >
        {text}
      </span>
    );
  }

  if (options) {
    return (
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onCommit(event.target.value)}
        className={clsx(face, "cursor-pointer pr-1")}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (draft === null) {
    return (
      <button
        type="button"
        aria-label={`${label}: ${text}. Press Enter to edit.`}
        onClick={() => setDraft(value)}
        className={clsx(face, "cursor-text hover:border-accent")}
      >
        {text || "ε"}
      </button>
    );
  }

  function finish(commit: boolean): void {
    if (commit && draft !== null && draft !== value) {
      onCommit(draft);
    }
    setDraft(null);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key === "Enter") {
      event.preventDefault();
      finish(true);
    } else if (event.key === "Escape") {
      event.preventDefault();
      finish(false);
    }
  }

  return (
    <input
      aria-label={label}
      autoFocus
      value={draft}
      size={Math.max(2, draft.length + 1)}
      onChange={(event) => setDraft(event.target.value)}
      onKeyDown={onKeyDown}
      onBlur={() => finish(true)}
      className={clsx(face, "border-accent bg-surface")}
    />
  );
}

/** A value the reading cannot show yet, because a clarification question is pending. */
export function MissingChip({ label }: { label: string }) {
  return (
    <span
      title={`${label}: answer the question below`}
      className={clsx(
        CHIP,
        "border-dashed border-amber bg-amber-soft font-medium text-amber",
      )}
    >
      ?<span className="sr-only">{label} not decided yet</span>
    </span>
  );
}
