import { describe, expect, it } from "vitest";
import { sanitizeSvg, svgSize } from "./svg";

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="300pt" height="90pt" viewBox="0 0 300 90" onload="alert(1)">
<script>alert(2)</script>
<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">html</div></foreignObject>
<g id="s-q0" class="node state" onmouseover="alert(3)">
<a xlink:href="javascript:alert(4)" xlink:title="start"><ellipse cx="10" cy="10" rx="5" ry="5"/></a>
</g>
<g id="a_s-q1"><a xlink:title="no a seen yet"><text>q1</text></a></g>
</svg>`;

describe("sanitizeSvg", () => {
  it("strips scripts, foreign objects, handlers and javascript: links", () => {
    const clean = sanitizeSvg(SVG);
    expect(clean).not.toMatch(
      /<script|foreignObject|onload|onmouseover|javascript:/i,
    );
    expect(clean).toContain('id="s-q0"');
    expect(clean).toContain('xlink:title="no a seen yet"');
    expect(clean).toContain('role="img"');
  });

  it("drops the fixed size so the drawing scales, keeping the viewBox", () => {
    const clean = sanitizeSvg(SVG);
    expect(clean).not.toMatch(/<svg[^>]*\swidth=/);
    expect(svgSize(clean)).toEqual({ width: 300, height: 90 });
  });

  it("refuses a document that is not SVG", () => {
    expect(() => sanitizeSvg("<html><body>hi</body></html>")).toThrow(
      "The diagram is not an SVG document.",
    );
  });
});
