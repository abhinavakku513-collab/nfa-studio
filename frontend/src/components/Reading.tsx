"use client";

import type { ReactNode } from "react";
import {
  type CountOp,
  OP_LABELS,
  type Path,
  formatSymbols,
  formatWords,
  parseWords,
} from "@/lib/studio/ir";
import { EditableChip, MissingChip } from "./EditableChip";

// The reading accepts complete IR and the partial IR of a pending question alike, so it
// reads fields defensively; a field that is still open is shown as a "?" chip.
type Loose = Record<string, unknown>;
type Edit = (path: Path, value: unknown) => void;

const OP_OPTIONS = (Object.keys(OP_LABELS) as CountOp[]).map((op) => ({ value: op, label: OP_LABELS[op] }));
const PARITY_OPTIONS = [
  { value: "even", label: "even" },
  { value: "odd", label: "odd" },
];
const OVERLAP_OPTIONS = [
  { value: "true", label: "overlapping allowed" },
  { value: "false", label: "disjoint occurrences" },
];

/** "Strings over {a, b} that …": the IR as a sentence whose values are editable chips. */
export function Reading({
  ir,
  onEdit,
  readOnly = false,
}: {
  ir: Loose;
  onEdit: Edit;
  readOnly?: boolean;
}) {
  const alphabet = ir.alphabet as Loose | undefined;
  const symbols = Array.isArray(alphabet?.symbols) ? (alphabet.symbols as string[]) : null;
  const language = ir.language as Loose | null | undefined;
  return (
    <div className="text-sm leading-8">
      Strings over{" "}
      <span className="font-mono">{symbols ? formatSymbols(symbols) : <MissingChip label="alphabet" />}</span>{" "}
      that{" "}
      {language ? (
        <Phrase node={language} path={["language"]} onEdit={onEdit} readOnly={readOnly} />
      ) : (
        <MissingChip label="grouping" />
      )}
    </div>
  );
}

function Phrase({
  node,
  path,
  onEdit,
  readOnly,
}: {
  node: Loose;
  path: Path;
  onEdit: Edit;
  readOnly: boolean;
}): ReactNode {
  function chip(key: string, label: string, extra: Partial<Parameters<typeof EditableChip>[0]> = {}) {
    const value = node[key];
    if (value === undefined || value === null) {
      return <MissingChip label={label} />;
    }
    return (
      <EditableChip
        label={label}
        value={String(value)}
        onCommit={(text) => onEdit([...path, key], text)}
        readOnly={readOnly}
        {...extra}
      />
    );
  }

  function numberChip(key: string, label: string) {
    return chip(key, label, {
      onCommit: (text) => {
        const n = Number.parseInt(text, 10);
        if (Number.isFinite(n)) {
          onEdit([...path, key], n);
        }
      },
    });
  }

  function children(intro: string): ReactNode {
    const items = Array.isArray(node.children) ? (node.children as Loose[]) : [];
    return (
      <>
        {intro}
        <ul className="ml-4 list-disc pl-4 marker:text-subtle">
          {items.map((child, i) => (
            <li key={i}>
              <Phrase node={child} path={[...path, "children", i]} onEdit={onEdit} readOnly={readOnly} />
            </li>
          ))}
        </ul>
      </>
    );
  }

  function nested(intro: string): ReactNode {
    const child = node.child as Loose | undefined;
    return (
      <>
        {intro}
        <ul className="ml-4 list-disc pl-4 marker:text-subtle">
          <li>
            {child ? (
              <Phrase node={child} path={[...path, "child"]} onEdit={onEdit} readOnly={readOnly} />
            ) : (
              <MissingChip label="condition" />
            )}
          </li>
        </ul>
      </>
    );
  }

  const pattern = (label: string) => chip("pattern", label, { mono: true });

  switch (node.type) {
    case "starts_with":
      return <>start with {pattern("prefix")}</>;
    case "ends_with":
      return <>end with {pattern("suffix")}</>;
    case "contains":
      return <>contain {pattern("substring")}</>;
    case "avoids":
      return <>do not contain {pattern("forbidden substring")}</>;
    case "symbol_count":
      return (
        <>
          contain {chip("op", "comparison", { options: OP_OPTIONS })} {numberChip("n", "count")}{" "}
          occurrences of {chip("symbol", "counted symbol", { mono: true })}
        </>
      );
    case "symbol_parity":
      return (
        <>
          contain an {chip("parity", "parity", { options: PARITY_OPTIONS })} number of{" "}
          {chip("symbol", "counted symbol", { mono: true })}
        </>
      );
    case "length_mod":
      return (
        <>
          have a length that leaves remainder {numberChip("r", "remainder")} when divided by{" "}
          {numberChip("m", "modulus")}
        </>
      );
    case "pattern_count":
      return (
        <>
          contain {pattern("counted pattern")} {chip("op", "comparison", { options: OP_OPTIONS })}{" "}
          {numberChip("n", "count")} times, counting{" "}
          {chip("overlap", "overlap", {
            options: OVERLAP_OPTIONS,
            onCommit: (text) => onEdit([...path, "overlap"], text === "true"),
          })}
        </>
      );
    case "regex":
      return <>match the regular expression {chip("expr", "regular expression", { mono: true })}</>;
    case "literal_set": {
      const words = Array.isArray(node.words) ? (node.words as string[]) : [];
      return (
        <>
          are exactly one of{" "}
          {chip("words", "listed words", {
            value: formatWords(words),
            mono: true,
            onCommit: (text) => onEdit([...path, "words"], parseWords(text)),
          })}
        </>
      );
    }
    case "and":
      return children("satisfy all of these:");
    case "or":
      return children("satisfy at least one of these:");
    case "concat":
      return children("split into consecutive parts that, in order,");
    case "not":
      return nested("do not satisfy this:");
    case "star":
      return nested("split into zero or more parts, each of which must");
    default:
      return <MissingChip label="condition" />;
  }
}
