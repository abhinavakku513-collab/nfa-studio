import { describe, expect, it } from "vitest";
import { ir } from "@/test/fakeServer";
import type { IRDocument } from "@/lib/api/client";
import { formatWords, parseSymbols, parseWords, setAt, withAlphabet } from "./ir";

describe("setAt", () => {
  it("replaces one value and copies only the path to it", () => {
    const root = { language: { type: "and", children: [{ pattern: "a" }, { pattern: "b" }] }, other: { x: 1 } };
    const next = setAt(root, ["language", "children", 1, "pattern"], "ba");
    expect(next.language.children[1].pattern).toBe("ba");
    expect(root.language.children[1].pattern).toBe("b");
    expect(next.other).toBe(root.other);
    expect(next.language.children[0]).toBe(root.language.children[0]);
  });
});

describe("alphabet and words", () => {
  it("parses symbols like the backend: sorted, unique", () => {
    expect(parseSymbols("{b, a ,b}")).toEqual(["a", "b"]);
    expect(parseSymbols("0 1")).toEqual(["0", "1"]);
    expect(parseSymbols("")).toEqual([]);
  });

  it("shows the empty word as ε and reads it back", () => {
    expect(formatWords(["", "ab"])).toBe("ε, ab");
    expect(parseWords("ε, ab, , b")).toEqual(["", "ab", "b"]);
  });

  it("a chosen alphabet is the user's, no longer an inferred assumption", () => {
    const doc = ir({ type: "contains", pattern: "a" }, [
      { id: "alphabet_inferred", text: "inferred", editable: true },
      { id: "zero_is_even", text: "zero", editable: false },
    ]) as IRDocument;
    const next = withAlphabet(doc, ["a", "b", "c"]);
    expect(next.alphabet).toEqual({ symbols: ["a", "b", "c"], source: "user" });
    expect(next.assumptions.map((a) => a.id)).toEqual(["zero_is_even"]);
  });
});
