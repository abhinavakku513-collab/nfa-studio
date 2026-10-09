import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "./page";

describe("Home", () => {
  it("renders the app name and the five-tuple with its math glyphs", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { name: "NFA Studio" })).toBeInTheDocument();
    expect(screen.getByText(/q₀/)).toHaveTextContent(/Σ.*δ.*ε.*∅/);
  });
});
