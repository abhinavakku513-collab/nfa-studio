import { describe, expect, it } from "vitest";
import { badSymbol, parseBatch, parseWord, showWord } from "./word";

describe("word input", () => {
  it("finds the first symbol outside Σ with its 1-based position", () => {
    expect(badSymbol("abba", ["a", "b"])).toBeNull();
    expect(badSymbol("abca", ["a", "b"])).toEqual({ position: 3, symbol: "c" });
    expect(badSymbol("a b", ["a", "b"])).toEqual({ position: 2, symbol: " " });
  });

  it("reads ε as the empty word", () => {
    expect(parseWord("ε")).toBe("");
    expect(parseWord("aε")).toBe("aε");
    expect(showWord("")).toBe("ε");
  });

  it("takes one word per line for a batch, skipping blank lines", () => {
    expect(parseBatch("ab\r\n\n  ba  \nε\n")).toEqual(["ab", "ba", ""]);
  });
});
