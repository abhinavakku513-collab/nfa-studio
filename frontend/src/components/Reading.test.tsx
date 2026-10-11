import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Reading } from "./Reading";

const starts = (pattern: string) => ({ type: "starts_with", pattern });
const ends = (pattern: string) => ({ type: "ends_with", pattern });
const contains = (pattern: string) => ({ type: "contains", pattern });

function renderReading(language: unknown) {
  render(
    <Reading
      ir={{ alphabet: { symbols: ["0", "1"] }, language }}
      onEdit={() => undefined}
      readOnly
    />,
  );
}

/** The direct conditions of a list, as their text. */
function items(list: HTMLElement): string[] {
  return within(list)
    .getAllByRole("listitem")
    .filter((item) => item.parentElement === list)
    .map((item) => item.textContent ?? "");
}

describe("Reading", () => {
  it("shows each joined condition as its own bullet, labelled with its join", () => {
    renderReading({
      type: "and",
      children: [contains("101"), ends("00")],
    });
    const [list] = screen.getAllByRole("list");
    expect(items(list)).toEqual([
      expect.stringMatching(/^contain .*101/),
      expect.stringMatching(/^and end with .*00/),
    ]);
  });

  it("shows the grouping of mixed and/or as nested labelled bullets", () => {
    renderReading({
      type: "or",
      children: [
        { type: "and", children: [starts("1"), ends("0")] },
        contains("11"),
      ],
    });
    const [outer, inner] = screen.getAllByRole("list");
    expect(items(outer)).toEqual([
      expect.stringMatching(/^satisfy all of these:/),
      expect.stringMatching(/^or contain .*11/),
    ]);
    expect(items(inner)).toEqual([
      expect.stringMatching(/^start with .*1/),
      expect.stringMatching(/^and end with .*0/),
    ]);
  });
});
