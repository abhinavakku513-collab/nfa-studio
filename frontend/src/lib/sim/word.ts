import { EPSILON } from "@/lib/studio/ir";

/** The word a user typed: "ε" on its own stands for the empty word. */
export function parseWord(text: string): string {
  return text === EPSILON ? "" : text;
}

export function showWord(word: string): string {
  return word === "" ? EPSILON : word;
}

export type BadSymbol = { position: number; symbol: string };

/** The first symbol outside Σ, with its 1-based position as the server reports it. */
export function badSymbol(
  word: string,
  alphabet: readonly string[],
): BadSymbol | null {
  const symbols = Array.from(word);
  const index = symbols.findIndex((symbol) => !alphabet.includes(symbol));
  return index < 0 ? null : { position: index + 1, symbol: symbols[index] };
}

/** Batch input: one word per line; blank lines are skipped, "ε" is the empty word. */
export function parseBatch(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line !== "")
    .map(parseWord);
}
