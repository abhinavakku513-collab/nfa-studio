import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { READY, SUMMARY, fakeServer, problem } from "@/test/fakeServer";
import { Studio } from "./Studio";

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
});

async function read(text: string): Promise<void> {
  const box = screen.getByLabelText(/describe a set of strings/i);
  fireEvent.change(box, { target: { value: text } });
  await act(async () => {
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });
  });
}

describe("Studio", () => {
  it("reads a description with Ctrl+Enter and shows it as an editable sentence", async () => {
    render(
      <Studio
        api={fakeServer({ "POST /v1/interpret": () => ({ json: READY }) }).api}
      />,
    );
    await read("exactly two a's");
    const confirm = screen.getByRole("region", { name: "Confirm" });
    expect(confirm).toHaveTextContent("Strings over {a, b} that contain");
    expect(
      within(confirm).getByRole("combobox", { name: "comparison" }),
    ).toHaveValue("eq");
    expect(
      within(confirm).getByRole("button", { name: /count: 2/ }),
    ).toBeInTheDocument();
  });

  it("edits a value from the keyboard: Enter opens it, Enter commits, Escape cancels", async () => {
    render(
      <Studio
        api={fakeServer({ "POST /v1/interpret": () => ({ json: READY }) }).api}
      />,
    );
    await read("exactly two a's");
    fireEvent.click(screen.getByRole("button", { name: /count: 2/ }));
    const input = screen.getByRole("textbox", { name: "count" });
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: "5" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(
      screen.getByRole("button", { name: /count: 5/ }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /counted symbol: a/ }));
    const symbol = screen.getByRole("textbox", { name: "counted symbol" });
    fireEvent.change(symbol, { target: { value: "b" } });
    fireEvent.keyDown(symbol, { key: "Escape" });
    expect(
      screen.getByRole("button", { name: /counted symbol: a/ }),
    ).toBeInTheDocument();
  });

  it("turning an assumption off pauses the build until it is back on", async () => {
    render(
      <Studio
        api={fakeServer({ "POST /v1/interpret": () => ({ json: READY }) }).api}
      />,
    );
    await read("exactly two a's");
    const build = screen.getByRole("button", { name: "Build and verify" });
    expect(build).toBeEnabled();
    const toggle = screen.getByRole("switch", {
      name: /alphabet was inferred/,
    });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(build).toBeDisabled();
    expect(
      screen.getByText(/Building waits while an assumption is off/),
    ).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(build).toBeEnabled();
    // Facts cannot be switched off.
    expect(
      screen.queryByRole("switch", { name: /Zero occurrences/ }),
    ).toBeNull();
  });

  it("says when the reading was proposed by the language model", async () => {
    const aiReading = {
      ...READY,
      ir: {
        ...READY.ir,
        assumptions: [
          {
            id: "llm_interpreted",
            text: "This reading was proposed by a language model; check it before building.",
            editable: false,
          },
        ],
      },
    };
    render(
      <Studio
        api={
          fakeServer({ "POST /v1/interpret": () => ({ json: aiReading }) }).api
        }
      />,
    );
    await read("a's counted twice, more or less");
    const confirm = screen.getByRole("region", { name: "Confirm" });
    expect(within(confirm).getByText("Read with AI help.")).toBeInTheDocument();
    // The same bullet reading follows, and the notice is not repeated as an assumption.
    expect(confirm).toHaveTextContent("Strings over {a, b} that");
    expect(
      within(confirm).queryByText(/proposed by a language model; check it/),
    ).toBeNull();
  });

  it("does not mark a reading the rules made", async () => {
    render(
      <Studio
        api={fakeServer({ "POST /v1/interpret": () => ({ json: READY }) }).api}
      />,
    );
    await read("exactly two a's");
    expect(screen.queryByText("Read with AI help.")).toBeNull();
  });

  it("builds and shows the badge with icon, level and evidence", async () => {
    const server = fakeServer({
      "POST /v1/interpret": () => ({ json: READY }),
      "POST /v1/automata": () => ({ json: SUMMARY }),
    });
    render(<Studio api={server.api} />);
    await read("exactly two a's");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Build and verify" }));
    });
    expect(
      screen.getByText("V2 · Exactly equivalent to reference"),
    ).toBeInTheDocument();
    const progress = screen.getByRole("list", { name: "Build progress" });
    expect(progress).toHaveTextContent("Compiled4 states · DFAdone");
    expect(progress).toHaveTextContent("Verifieddone");
    expect(screen.getByRole("region", { name: "Automaton" })).toHaveTextContent(
      "sha256:abc123",
    );
  });

  it("answers a clarification with a button", async () => {
    const server = fakeServer({
      "POST /v1/interpret": () => ({
        json: {
          status: "clarification_required",
          session_id: "s_9",
          confidence: 1,
          question: {
            id: "Q1",
            topic: "count_exact_or_at_least",
            text: "Exactly 2 a's, or at least 2?",
            options: [
              { id: "exactly", label: "Exactly 2" },
              { id: "at_least", label: "At least 2" },
              { id: "edit", label: "Edit manually" },
            ],
          },
          partial_ir: {
            alphabet: { symbols: ["a", "b"] },
            language: { type: "symbol_count", symbol: "a", n: 2 },
          },
        },
      }),
      "POST /v1/interpret/s_9/answer": () => ({ json: READY }),
    });
    render(<Studio api={server.api} />);
    await read("contains two a's");
    const group = screen.getByRole("group", {
      name: "Exactly 2 a's, or at least 2?",
    });
    expect(screen.getByText("comparison not decided yet")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(group).getByRole("button", { name: "Exactly 2" }));
    });
    expect(server.requests[1].body).toEqual({
      question_id: "Q1",
      option_id: "exactly",
    });
    expect(screen.getByRole("combobox", { name: "comparison" })).toHaveValue(
      "eq",
    );
  });

  it("shows the reason and next action of an error, and its examples fill the text box", async () => {
    const message =
      "Could not read 'strings that are good' as a description of strings. Use phrases such as 'starts with'.";
    const server = fakeServer({
      "POST /v1/interpret": () =>
        problem("E_UNSUPPORTED_FEATURE", message, {
          reason: "not_interpretable",
          examples: ["binary strings ending in 01"],
          alternative: null,
        }),
    });
    render(<Studio api={server.api} />);
    await read("strings that are good");
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("This description cannot be read");
    expect(alert).toHaveTextContent(message);
    fireEvent.click(
      within(alert).getByRole("button", {
        name: "binary strings ending in 01",
      }),
    );
    expect(screen.getByLabelText(/describe a set of strings/i)).toHaveValue(
      "binary strings ending in 01",
    );
  });

  it("offers a non-regular request's regular alternative", async () => {
    const alternative = {
      ir_version: "1.0",
      alphabet: { symbols: ["a", "b"], source: "user" },
      language: { type: "literal_set", words: ["", "ab", "aabb"] },
    };
    const server = fakeServer({
      "POST /v1/interpret": () =>
        problem(
          "E_UNSUPPORTED_NONREGULAR",
          "This language is not regular: it needs to count without a bound. Try aⁿbⁿ with n ≤ 2.",
          {
            reason: "power_counting",
            alternative: { text: "Try aⁿbⁿ with n ≤ 2.", ir: alternative },
          },
        ),
    });
    render(<Studio api={server.api} />);
    await read("aⁿbⁿ for all n");
    fireEvent.click(
      screen.getByRole("button", { name: "Use the regular alternative" }),
    );
    expect(screen.getByRole("region", { name: "Confirm" })).toHaveTextContent(
      "are exactly one of",
    );
    expect(
      screen.getByRole("button", { name: /listed words: ε, ab, aabb/ }),
    ).toBeInTheDocument();
  });

  it("switches between light and dark themes", async () => {
    document.documentElement.dataset.theme = "light";
    render(<Studio api={fakeServer({}).api} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Switch to dark theme" }),
    );
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("nfa-theme")).toBe("dark");
    // The toggle follows <html data-theme> through a MutationObserver, which fires async.
    expect(
      await screen.findByRole("button", { name: "Switch to light theme" }),
    ).toBeInTheDocument();
  });
});
