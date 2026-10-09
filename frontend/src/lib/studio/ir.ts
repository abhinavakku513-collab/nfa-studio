import type { IRDocument } from "@/lib/api/client";

export type Path = readonly (string | number)[];
export type CountOp = "eq" | "ge" | "le";

export const OP_LABELS: Record<CountOp, string> = {
  eq: "exactly",
  ge: "at least",
  le: "at most",
};

export const EPSILON = "ε";

/** A copy of `root` with the value at `path` replaced; the original is left untouched. */
export function setAt<T>(root: T, path: Path, value: unknown): T {
  if (path.length === 0) {
    return value as T;
  }
  const [head, ...rest] = path;
  if (Array.isArray(root)) {
    const copy = [...root];
    copy[head as number] = setAt(copy[head as number], rest, value);
    return copy as T;
  }
  const record = root as Record<string, unknown>;
  return { ...record, [head]: setAt(record[head as string], rest, value) } as T;
}

/** "a, b c" or "{a,b}" → ["a", "b", "c"]: sorted and without duplicates, like the backend. */
export function parseSymbols(text: string): string[] {
  const symbols = text
    .replace(/[{}]/g, " ")
    .split(/[\s,]+/)
    .filter((symbol) => symbol.length > 0);
  return [...new Set(symbols)].sort();
}

export function formatSymbols(symbols: readonly string[]): string {
  return `{${symbols.join(", ")}}`;
}

/** Words of a literal set as typed by a person: "" is shown and read back as ε. */
export function formatWords(words: readonly string[]): string {
  return words.map((word) => (word === "" ? EPSILON : word)).join(", ");
}

export function parseWords(text: string): string[] {
  return text
    .split(",")
    .map((word) => word.trim())
    .filter((word) => word.length > 0)
    .map((word) => (word === EPSILON ? "" : word));
}

/** A new IR with a user-chosen alphabet; it is no longer an inferred assumption. */
export function withAlphabet(ir: IRDocument, symbols: string[]): IRDocument {
  return {
    ...ir,
    alphabet: { symbols, source: "user" },
    assumptions: ir.assumptions.filter((assumption) => assumption.id !== "alphabet_inferred"),
  };
}
