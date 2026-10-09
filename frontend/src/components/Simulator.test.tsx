import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StudioProvider } from "@/lib/studio/context";
import { fakeServer } from "@/test/fakeServer";
import { Simulator } from "./Simulator";

const ID = "sha256:abc123";

// q0 -a-> q1 -b-> q2 (accepting); anything else empties the active set.
const MOVES: Record<string, string> = { "q0 a": "q1", "q1 b": "q2" };

type Step = {
  index: number;
  symbol: string | null;
  moved: string[];
  after: string[];
  accepting_present: boolean;
  final_accepted: boolean | null;
  transitions: string[][];
  epsilon_layers: string[][][];
};

function trace(word: string) {
  let active = ["q0"];
  const steps: Step[] = [
    {
      index: 0,
      symbol: null,
      moved: ["q0"],
      after: active,
      accepting_present: false,
      final_accepted: null,
      transitions: [],
      epsilon_layers: [],
    },
  ];
  for (const [i, symbol] of Array.from(word).entries()) {
    const transitions = active.flatMap((q) =>
      MOVES[`${q} ${symbol}`] ? [[q, symbol, MOVES[`${q} ${symbol}`]]] : [],
    );
    active = transitions.map(([, , r]) => r);
    steps.push({
      index: i + 1,
      symbol,
      moved: active,
      after: active,
      accepting_present: active.includes("q2"),
      final_accepted: null,
      transitions,
      epsilon_layers: [],
    });
  }
  const accepted = active.includes("q2");
  return {
    automaton_id: ID,
    word,
    valid: true,
    accepted,
    witness: accepted
      ? [
          ["q0", "a", "q1"],
          ["q1", "b", "q2"],
        ]
      : null,
    steps,
    page: 1,
    pages: 1,
    total_steps: steps.length,
  };
}

function renderSimulator() {
  const server = fakeServer({
    [`GET /v1/automata/${ID}`]: () => ({
      json: {
        automaton_id: ID,
        five_tuple: {
          Q: ["q0", "q1", "q2"],
          Sigma: ["a", "b"],
          delta: [],
          q0: "q0",
          F: ["q2"],
        },
      },
    }),
    [`POST /v1/automata/${ID}/simulate`]: (body) => ({
      json: trace((body as { word: string }).word),
    }),
    [`POST /v1/automata/${ID}/simulate/batch`]: () => ({
      json: {
        automaton_id: ID,
        results: [
          { word: "ab", valid: true, accepted: true, error: null },
          { word: "ba", valid: true, accepted: false, error: null },
          {
            word: "ac",
            valid: false,
            accepted: null,
            error: {
              code: "E_SYMBOL_NOT_IN_ALPHABET",
              message:
                "'c' at position 2 is not in the alphabet {a, b}. Use only these symbols.",
              detail: { symbol: "c", position: 2 },
            },
          },
        ],
      },
    }),
  });
  render(
    <StudioProvider api={server.api}>
      <Simulator
        automatonId={ID}
        geometry={null}
        idMap={{}}
        accepting={new Set(["q2"])}
        note={null}
      />
    </StudioProvider>,
  );
  return server;
}

async function simulate(word: string): Promise<void> {
  const input = screen.getByLabelText("Word to simulate");
  fireEvent.change(input, { target: { value: word } });
  await act(async () => {
    fireEvent.submit(input);
  });
}

const status = () => screen.getByText(/^Step \d+:/);

/** The verdict chip, once the animation has reached the last step. */
async function findVerdict(text: string): Promise<HTMLElement> {
  const chip = await screen.findByRole(
    "status",
    { name: "Verdict" },
    { timeout: 3000 },
  );
  expect(chip).toHaveTextContent(text);
  return chip;
}

beforeEach(() => {
  // Reduced motion: states change instantly and only the hold between steps takes time.
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Simulator", () => {
  it("checks the word against Σ as it is typed and points at the bad symbol", async () => {
    renderSimulator();
    await screen.findByText(/Σ = \{a, b\}/);
    const input = screen.getByLabelText("Word to simulate");
    fireEvent.change(input, { target: { value: "abca" } });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(
      screen.getByText(/Position 3: “c” is not in Σ = \{a, b\}/),
    ).toBeInTheDocument();
    expect(screen.getByText("c", { selector: "mark" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Simulate" })).toBeDisabled();

    fireEvent.change(input, { target: { value: "ab" } });
    expect(input).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByRole("button", { name: "Simulate" })).toBeEnabled();
  });

  it("plays a word to its verdict and announces every step", async () => {
    const { requests } = renderSimulator();
    await screen.findByText(/Σ = \{a, b\}/);
    await simulate("ab");
    expect(requests.at(-1)?.body).toEqual({
      word: "ab",
      witness: true,
      page: 1,
    });

    expect(await findVerdict("Accepted")).toBeInTheDocument();
    expect(status()).toHaveTextContent(
      "Step 2: read b, active {q2}. Accepted.",
    );
    expect(status()).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("button", { name: "Play (Space)" })).toBeEnabled();
  });

  it("steps with the keyboard: Home, →, ←, End", async () => {
    renderSimulator();
    await screen.findByText(/Σ = \{a, b\}/);
    await simulate("ab");
    await screen.findByText(/^Step 2:/, {}, { timeout: 3000 });

    const tape = screen.getByRole("group", { name: /Input tape/ });
    fireEvent.keyDown(tape, { key: "Home" });
    expect(status()).toHaveTextContent("Step 0: start, active {q0}");
    fireEvent.keyDown(tape, { key: "ArrowRight" });
    expect(status()).toHaveTextContent("Step 1: read a, active {q1}");
    expect(tape).toHaveAccessibleName(/1 of 2 symbols read/);
    fireEvent.keyDown(tape, { key: "ArrowLeft" });
    expect(status()).toHaveTextContent("Step 0: start, active {q0}");
    fireEvent.keyDown(tape, { key: "End" });
    expect(status()).toHaveTextContent(
      "Step 2: read b, active {q2}. Accepted.",
    );
    expect(screen.getByRole("slider", { name: "Step" })).toHaveValue("2");
  });

  it("shows a rejection, keeps a history and re-runs from it", async () => {
    const { requests } = renderSimulator();
    await screen.findByText(/Σ = \{a, b\}/);
    await simulate("ba");
    expect(await findVerdict("Rejected")).toHaveClass("sim-shake");
    expect(status()).toHaveTextContent("Step 2: read a, active ∅. Rejected.");

    await simulate("ab");
    await screen.findByText(/Accepted\.$/, {}, { timeout: 3000 });
    const history = screen.getByRole("region", { name: "Tested words" });
    const items = within(history).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining("Acceptedab"),
      expect.stringContaining("Rejectedba"),
    ]);

    await act(async () => {
      fireEvent.click(
        within(history).getByRole("button", { name: "Run ba again" }),
      );
    });
    expect(requests.at(-1)?.body).toMatchObject({ word: "ba" });
    expect(screen.getByLabelText("Word to simulate")).toHaveValue("ba");
  });

  it("runs a batch of words and tabulates the results", async () => {
    const { requests } = renderSimulator();
    fireEvent.click(screen.getByText("Batch test"));
    fireEvent.change(screen.getByLabelText(/Words, one per line/), {
      target: { value: "ab\nba\n\nac\n" },
    });
    expect(screen.getByText("3 words")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run batch" }));
    });
    expect(requests.at(-1)?.body).toEqual({ words: ["ab", "ba", "ac"] });
    expect(
      screen.getByText("1 accepted, 1 rejected, 1 invalid"),
    ).toBeInTheDocument();
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows.map((row) => row.textContent)).toEqual([
      "abAcceptedSimulate",
      "baRejectedSimulate",
      expect.stringContaining("ac'c' at position 2 is not in the alphabet"),
    ]);
  });

  it("refuses a batch over 100 words before sending it", () => {
    renderSimulator();
    fireEvent.click(screen.getByText("Batch test"));
    fireEvent.change(screen.getByLabelText(/Words, one per line/), {
      target: { value: Array.from({ length: 101 }, () => "ab").join("\n") },
    });
    expect(screen.getByText(/101 words; the limit is 100/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run batch" })).toBeDisabled();
  });
});
