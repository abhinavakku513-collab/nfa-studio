import { describe, expect, it } from "vitest";
import type { LogEntry } from "@/lib/api/client";
import { mathName, mathSet, provenance } from "./math";

function log(...nodes: string[]): LogEntry[] {
  return nodes.map((node) => ({ node, text: `${node} step`, states: 2 }));
}

describe("mathName and mathSet", () => {
  it("writes state numbers as subscripts", () => {
    expect(mathName("q0")).toBe("q₀");
    expect(mathName("q12")).toBe("q₁₂");
    expect(mathName("dead")).toBe("dead");
  });

  it("writes the empty set as ∅", () => {
    expect(mathSet([])).toBe("∅");
    expect(mathSet(["q0", "q3"])).toBe("{q₀, q₃}");
  });
});

describe("provenance (spec §7.3)", () => {
  it("says a complemented machine is a DFA from subset construction", () => {
    expect(provenance("dfa", log("contains", "not", "naming"))).toBe(
      "The displayed machine is a DFA produced by subset construction and complement, not a hand-built NFA.",
    );
  });

  it("says when only a part was complemented", () => {
    expect(
      provenance("nfa", log("contains", "not", "starts_with", "and")),
    ).toMatch(
      /^The displayed machine is an NFA\. Its "not" parts were produced by subset construction/,
    );
  });

  it("says a directly built machine needed no subset construction", () => {
    expect(provenance("enfa", log("regex"))).toBe(
      "The displayed machine is an ε-NFA built directly from the description; no subset construction was needed.",
    );
    expect(provenance("dfa", log("symbol_count"))).toMatch(
      /^The displayed machine is a DFA as built/,
    );
  });
});
