import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StudioProvider } from "@/lib/studio/context";
import { fakeServer } from "@/test/fakeServer";
import { Branches } from "./Branches";
import { DiagramTab } from "./DiagramTab";
import { Simulator } from "./Simulator";

const ID = "sha256:abc123";
const BASE = `/v1/automata/${ID}`;

type Machine = {
  label: string;
  states: string[];
  accepting: string[];
  delta: Record<string, string[]>;
};

// The ε-free NFAs the backend builds for contains 101 and ends_with 00 (compile/atoms).
const CONTAINS_101: Machine = {
  label: "contain 101",
  states: ["q0", "q1", "q2", "q3"],
  accepting: ["q3"],
  delta: {
    "q0 0": ["q0"],
    "q0 1": ["q0", "q1"],
    "q1 0": ["q2"],
    "q2 1": ["q3"],
    "q3 0": ["q3"],
    "q3 1": ["q3"],
  },
};
const ENDS_00: Machine = {
  label: "end with 00",
  states: ["q0", "q1", "q2"],
  accepting: ["q2"],
  delta: { "q0 0": ["q0", "q1"], "q0 1": ["q0"], "q1 0": ["q2"] },
};
const LANES = [CONTAINS_101, ENDS_00];

function run(machine: Machine, word: string): string[][] {
  let active = ["q0"];
  const sets = [active];
  for (const symbol of word) {
    const next = new Set(
      active.flatMap((q) => machine.delta[`${q} ${symbol}`] ?? []),
    );
    active = machine.states.filter((q) => next.has(q));
    sets.push(active);
  }
  return sets;
}

function accepts(machine: Machine, active: readonly string[]): boolean {
  return active.some((q) => machine.accepting.includes(q));
}

function svg(machine: Machine): string {
  const states = machine.states
    .map(
      (q, i) =>
        `<g id="s-${q}" class="node state"><title>${q}</title><ellipse cx="${40 + 60 * i}" cy="30" rx="16" ry="16"/><text x="${40 + 60 * i}" y="34">${q}</text></g>`,
    )
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="300pt" height="60pt" viewBox="0 0 300 60">${states}</svg>`;
}

function branches(combiner: "all" | "any", lanes = LANES) {
  return {
    automaton_id: ID,
    combiner,
    branches: lanes.map((machine, index) => ({
      index,
      label: machine.label,
      negated: false,
      automaton_id: `sha256:lane${index}`,
      kind: "nfa" as const,
      state_count: machine.states.length,
      svg: svg(machine),
      graph: {
        model_hash: `sha256:lane${index}`,
        eps_free: false,
        start_edge: { id: "start-edge", target: "q0" },
        nodes: machine.states.map((q) => ({
          id: `s-${q}`,
          name: q,
          start: q === "q0",
          accepting: machine.accepting.includes(q),
          dead: false,
          meaning: q,
          short_meaning: q,
        })),
        edges: [],
        id_map: { states: {}, transitions: {} },
        hidden_dead_states: [],
      },
    })),
  };
}

function routes(combiner: "all" | "any") {
  const verdicts = (word: string) =>
    LANES.map((machine) => accepts(machine, run(machine, word).at(-1) ?? []));
  const combine = (values: boolean[]) =>
    combiner === "all" ? values.every(Boolean) : values.some(Boolean);
  return {
    [`GET ${BASE}`]: () => ({
      json: {
        automaton_id: ID,
        five_tuple: {
          Q: [],
          Sigma: ["0", "1"],
          delta: [],
          q0: "q0",
          F: [],
        },
      },
    }),
    [`POST ${BASE}/simulate`]: (body: unknown) => {
      const word = (body as { word: string }).word;
      const steps = [null, ...Array.from(word)].map((symbol, index) => ({
        index,
        symbol,
        moved: ["q0"],
        after: ["q0"],
        accepting_present: false,
        final_accepted: null,
        transitions: [],
        epsilon_layers: [],
      }));
      return {
        json: {
          automaton_id: ID,
          word,
          valid: true,
          accepted: combine(verdicts(word)),
          witness: null,
          steps,
          page: 1,
          pages: 1,
          total_steps: steps.length,
        },
      };
    },
    [`POST ${BASE}/branches/simulate`]: (body: unknown) => {
      const word = (body as { word: string }).word;
      const runs = LANES.map((machine) => run(machine, word));
      const steps = runs[0].map((_, index) => {
        const accepting = LANES.map((machine, i) =>
          accepts(machine, runs[i][index]),
        );
        return {
          index,
          symbol: index === 0 ? null : word[index - 1],
          active: runs.map((sets) => sets[index]),
          accepting,
          combined: combine(accepting),
        };
      });
      return {
        json: {
          automaton_id: ID,
          word,
          combiner,
          accepted: verdicts(word),
          combined: combine(verdicts(word)),
          steps,
          page: 1,
          pages: 1,
          total_steps: steps.length,
        },
      };
    },
  };
}

function renderBranches(combiner: "all" | "any") {
  const server = fakeServer(routes(combiner));
  render(
    <StudioProvider api={server.api}>
      <Branches data={branches(combiner)} />
      <Simulator
        automatonId={ID}
        geometry={null}
        idMap={{}}
        accepting={new Set()}
        note={null}
        tape={false}
      />
    </StudioProvider>,
  );
  return server;
}

async function simulate(word: string): Promise<void> {
  await screen.findByText(/Σ = \{0, 1\}/);
  const input = screen.getByLabelText("Word to simulate");
  fireEvent.change(input, { target: { value: word } });
  await act(async () => {
    fireEvent.submit(input);
  });
}

const lane = (n: number) =>
  screen.getByRole("region", { name: new RegExp(`^Branch ${n}: `) });

/** The combiner's live text, once the last step has been reached. */
async function verdict(text: RegExp): Promise<void> {
  await waitFor(
    () => expect(screen.getByText(/^Combined verdict/)).toHaveTextContent(text),
    { timeout: 3000 },
  );
}

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Branches", () => {
  it("names every lane and says how the lanes combine", () => {
    renderBranches("all");
    expect(lane(1)).toHaveAccessibleName("Branch 1: contain 101");
    expect(lane(2)).toHaveAccessibleName("Branch 2: end with 00");
    expect(
      screen.getByRole("group", { name: /^2 branches; every branch must/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("ALL must accept")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "" })).toBeEmptyDOMElement();
  });

  it("10100: both lanes accept and ALL accepts", async () => {
    renderBranches("all");
    await simulate("10100");
    await verdict(/^Combined verdict: accepted; every branch must accept/);
    expect(within(lane(1)).getByText("Accepts")).toBeInTheDocument();
    expect(within(lane(2)).getByText("Accepts")).toBeInTheDocument();
    expect(screen.getByText("ALL must accept")).toHaveClass("bg-accent-soft");
  });

  it("101: lane 2 rejects, so the verdict is reject", async () => {
    renderBranches("all");
    await simulate("101");
    await verdict(
      /^Combined verdict: rejected; .*branch 2 \(end with 00\) rejects/,
    );
    expect(within(lane(1)).getByText("Accepts")).toBeInTheDocument();
    expect(within(lane(2)).getByText("Rejects")).toBeInTheDocument();
    expect(screen.getByText("ALL must accept")).toHaveClass("bg-danger-soft");
  });

  it("10101: lane 1 accepts, lane 2 rejects, the verdict is reject", async () => {
    renderBranches("all");
    await simulate("10101");
    await verdict(/^Combined verdict: rejected/);
    expect(within(lane(1)).getByText("Accepts")).toBeInTheDocument();
    expect(within(lane(2)).getByText("Rejects")).toBeInTheDocument();
  });

  it("the step controls move every lane together", async () => {
    renderBranches("all");
    await simulate("101");
    await verdict(/rejected/);
    const tape = screen.getByRole("group", { name: /Input tape/ });
    const active = (n: number) =>
      Array.from(lane(n).querySelectorAll(".is-active")).map((g) => g.id);

    fireEvent.keyDown(tape, { key: "Home" });
    await waitFor(() =>
      expect(within(lane(1)).getByText("{q0}")).toBeVisible(),
    );
    expect(within(lane(2)).getByText("{q0}")).toBeVisible();
    expect(active(1)).toEqual(["lane0-s-q0"]);
    expect(active(2)).toEqual(["lane1-s-q0"]);
    // Stepping back hides the verdicts until the end is reached again.
    expect(within(lane(1)).queryByText("Accepts")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Step forward (→)" }));
    await waitFor(() =>
      expect(within(lane(1)).getByText("{q0, q1}")).toBeVisible(),
    );
    expect(within(lane(2)).getByText("{q0}")).toBeVisible();
    expect(active(1)).toEqual(["lane0-s-q0", "lane0-s-q1"]);

    fireEvent.keyDown(tape, { key: "End" });
    await waitFor(() =>
      expect(
        within(lane(1)).getByText("{q0, q1, q3} · accepting"),
      ).toBeVisible(),
    );
    expect(within(lane(2)).getByText("{q0}")).toBeVisible();
    expect(screen.getByRole("slider", { name: "Step" })).toHaveValue("3");
  });

  it("ANY accepts when one lane does, with no ε-moves drawn between the lanes", async () => {
    renderBranches("any");
    expect(
      screen.getByRole("group", {
        name: "2 branches; one accepting branch is enough",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("ε")).toBeNull();
    await simulate("101");
    await verdict(
      /^Combined verdict: accepted; .*branch 1 \(contain 101\) accepts/,
    );
    expect(screen.getByText("ANY accepts")).toHaveClass("bg-accent-soft");
  });
});

describe("DiagramTab with branches", () => {
  const diagram = {
    [`GET ${BASE}/diagram`]: (_: unknown, url: URL) =>
      url.searchParams.get("format") === "svg"
        ? { text: svg(ENDS_00), type: "image/svg+xml" }
        : { json: branches("all").branches[1].graph },
  };

  it("offers the Branches view for two or more conditions", async () => {
    const server = fakeServer({
      ...routes("all"),
      ...diagram,
      [`GET ${BASE}/branches`]: () => ({ json: branches("all") }),
    });
    render(
      <StudioProvider api={server.api}>
        <DiagramTab id={ID} hasEpsilon={false} />
      </StudioProvider>,
    );
    const toggle = await screen.findByRole("button", { name: "Branches (2)" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(lane(1)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /ε-free/ })).toBeNull();

    // The same input box runs the word on every lane.
    await simulate("10100");
    await verdict(/accepted/);
    expect(server.requests.map((r) => r.route)).toContain(
      `POST ${BASE}/branches/simulate`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Whole automaton" }));
    expect(screen.queryByRole("region", { name: /^Branch 1/ })).toBeNull();
  });

  it("has no Branches view for a single condition", async () => {
    const server = fakeServer({
      ...routes("all"),
      ...diagram,
      [`GET ${BASE}/branches`]: () => ({
        json: { automaton_id: ID, combiner: null, branches: [] },
      }),
    });
    render(
      <StudioProvider api={server.api}>
        <DiagramTab id={ID} hasEpsilon={false} />
      </StudioProvider>,
    );
    await waitFor(() =>
      expect(server.requests.map((r) => r.route)).toContain(
        `GET ${BASE}/branches`,
      ),
    );
    await screen.findByRole("group", { name: /^Automaton with 3 states/ });
    expect(screen.queryByRole("button", { name: /^Branches/ })).toBeNull();
  });
});
