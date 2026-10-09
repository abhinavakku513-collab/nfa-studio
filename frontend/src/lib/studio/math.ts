import type { LogEntry } from "@/lib/api/client";

const SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉";

/** "q12" → "q₁₂": state names as they are typeset in the formal definition. */
export function mathName(name: string): string {
  return name.replace(
    /^(\D+)(\d+)$/,
    (_, head: string, digits: string) =>
      head +
      [...digits].map((digit) => SUBSCRIPT_DIGITS[Number(digit)]).join(""),
  );
}

export function mathSet(names: readonly string[]): string {
  return names.length === 0 ? "∅" : `{${names.map(mathName).join(", ")}}`;
}

/**
 * How the displayed machine came about (spec §7.3): whether it is a DFA from subset
 * construction and complement, or a hand-built NFA, read off the construction log.
 */
export function provenance(
  kind: "enfa" | "nfa" | "dfa",
  log: readonly LogEntry[],
): string {
  const steps = log.filter((entry) => entry.node !== "naming");
  const root = steps.at(-1)?.node;
  const complemented = steps.some((entry) => entry.node === "not");
  if (root === "not") {
    return "The displayed machine is a DFA produced by subset construction and complement, not a hand-built NFA.";
  }
  const built = { enfa: "an ε-NFA", nfa: "an NFA", dfa: "a DFA" }[kind];
  if (complemented) {
    return `The displayed machine is ${built}. Its "not" parts were produced by subset construction and complement, then combined with the rest.`;
  }
  if (kind === "dfa") {
    return "The displayed machine is a DFA as built: every construction step was already deterministic, so no subset construction was needed.";
  }
  return `The displayed machine is ${built} built directly from the description; no subset construction was needed.`;
}
