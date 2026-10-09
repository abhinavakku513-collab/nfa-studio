import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync("src/app/globals.css", "utf8");

function tokens(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    Array.from(body.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/g), (m) => [
      m[1],
      m[2],
    ]),
  );
}

const LIGHT = tokens(":root");
const THEMES = {
  light: LIGHT,
  dark: { ...LIGHT, ...tokens(':root[data-theme="dark"]') },
};

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

// Every text colour on every background it is used on (WCAG 1.4.3, 4.5:1).
const TEXT: [string, string][] = [
  ...["text", "muted", "subtle"].flatMap((fg) =>
    ["bg", "surface", "surface-2"].map((bg): [string, string] => [fg, bg]),
  ),
  ["accent", "surface"],
  ["accent", "bg"],
  ["accent-strong", "accent-soft"],
  ["text", "accent-soft"],
  ["accent-ink", "accent"],
  ["danger", "surface"],
  ["danger", "danger-soft"],
  ["amber", "amber-soft"],
  ["amber", "surface"],
  // Witness edge labels on the diagram background.
  ["amber", "bg"],
];

// Control outlines, focus rings, the witness path and active states (WCAG 1.4.11, 3:1).
const GRAPHICS: [string, string][] = [
  ...["bg", "surface", "surface-2"].map((bg): [string, string] => [
    "control-border",
    bg,
  ]),
  ["focus", "bg"],
  ["focus", "surface"],
  ["witness", "bg"],
  ["accent", "bg"],
  ["accent-strong", "bg"],
  ["text", "bg"],
];

describe.each(Object.entries(THEMES))("%s theme contrast", (_, theme) => {
  it.each(TEXT)("text %s on %s reaches 4.5:1", (fg, bg) => {
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(GRAPHICS)("%s on %s reaches 3:1", (fg, bg) => {
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(3);
  });
});
