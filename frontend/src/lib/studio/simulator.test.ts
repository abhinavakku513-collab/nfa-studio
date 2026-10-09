import { describe, expect, it, vi } from "vitest";
import { fakeServer, problem } from "@/test/fakeServer";
import { createSimulatorStore, stepAt } from "./simulator";

const ID = "sha256:abc123";
const SIMULATE = `POST /v1/automata/${ID}/simulate`;
const PAGE = 200;

/** A one-state machine over {a} that loops on a: every word is accepted. */
function trace(word: string, page = 1) {
  const total = word.length + 1;
  const steps = Array.from({ length: total }, (_, index) => ({
    index,
    symbol: index === 0 ? null : word[index - 1],
    moved: ["q0"],
    after: ["q0"],
    accepting_present: true,
    final_accepted: index === total - 1 ? true : null,
    transitions: index === 0 ? [] : [["q0", "a", "q0"]],
    epsilon_layers: [],
  }));
  return {
    automaton_id: ID,
    word,
    valid: true,
    accepted: true,
    witness: [],
    steps: steps.slice((page - 1) * PAGE, page * PAGE),
    page,
    pages: Math.ceil(total / PAGE),
    total_steps: total,
  };
}

function setup() {
  const server = fakeServer({
    [SIMULATE]: (body) => {
      const { word, page } = body as { word: string; page: number };
      return word.includes("c")
        ? problem(
            "E_SYMBOL_NOT_IN_ALPHABET",
            "'c' at position 2 is not in the alphabet {a}. Use only these symbols.",
            { symbol: "c", position: 2 },
          )
        : { json: trace(word, page) };
    },
    [`POST /v1/automata/${ID}/simulate/batch`]: (body) => ({
      json: {
        automaton_id: ID,
        results: (body as { words: string[] }).words.map((word) => ({
          word,
          valid: true,
          accepted: word.length % 2 === 0,
          error: null,
        })),
      },
    }),
  });
  const store = createSimulatorStore(server.api);
  store.getState().open(ID);
  return { store, requests: server.requests };
}

describe("simulator store", () => {
  it("runs a word from step 0, playing, and records it in the history", async () => {
    const { store, requests } = setup();
    await store.getState().run("aa");
    await store.getState().run("a");
    await store.getState().run("aa");
    const state = store.getState();
    expect(requests.at(-1)?.body).toEqual({
      word: "aa",
      witness: true,
      page: 1,
    });
    expect(state.trace?.total).toBe(3);
    expect(state.position).toBe(0);
    expect(state.motion).toBe("forward");
    expect(state.playing).toBe(true);
    expect(state.history).toEqual([
      { word: "aa", accepted: true },
      { word: "a", accepted: true },
    ]);
  });

  it("animates single steps forward and jumps everywhere else", async () => {
    const { store } = setup();
    await store.getState().run("aaa");
    const seq = () => store.getState().seq;
    const before = seq();
    store.getState().stepForward();
    expect(store.getState()).toMatchObject({
      position: 1,
      motion: "forward",
      playing: false,
    });
    store.getState().toEnd();
    expect(store.getState()).toMatchObject({ position: 3, motion: "jump" });
    store.getState().stepBack();
    expect(store.getState()).toMatchObject({ position: 2, motion: "jump" });
    store.getState().seek(99);
    expect(store.getState().position).toBe(3);
    expect(seq()).toBe(before + 4);
  });

  it("plays to the end, stops there, and plays again from the start", async () => {
    const { store } = setup();
    await store.getState().run("aa");
    store.getState().advance();
    store.getState().advance();
    expect(store.getState()).toMatchObject({ position: 2, playing: true });
    store.getState().advance();
    expect(store.getState().playing).toBe(false);
    store.getState().togglePlay();
    expect(store.getState()).toMatchObject({
      position: 0,
      playing: true,
      motion: "forward",
    });
    store.getState().togglePlay();
    expect(store.getState()).toMatchObject({ playing: false, motion: "jump" });
  });

  it("loads trace pages of 200 steps as the position reaches them (spec §9.3)", async () => {
    const { store, requests } = setup();
    const word = "a".repeat(450);
    await store.getState().run(word);
    expect(store.getState().trace).toMatchObject({
      total: 451,
      pages: 3,
      pageSize: 200,
    });
    expect(stepAt(store.getState().trace, 199)?.index).toBe(199);
    expect(stepAt(store.getState().trace, 200)).toBeUndefined();

    store.getState().seek(420);
    await vi.waitFor(() =>
      expect(stepAt(store.getState().trace, 420)?.index).toBe(420),
    );
    expect(requests.at(-1)?.body).toEqual({ word, witness: true, page: 3 });
    expect(stepAt(store.getState().trace, 300)).toBeUndefined();
  });

  it("shows the server's reason when a word cannot be read", async () => {
    const { store } = setup();
    await store.getState().run("acb");
    expect(store.getState().trace).toBeNull();
    expect(store.getState().problem?.code).toBe("E_SYMBOL_NOT_IN_ALPHABET");
  });

  it("runs a batch and starts afresh for another automaton", async () => {
    const { store, requests } = setup();
    await store.getState().runBatch(["", "a", "aa"]);
    expect(requests.at(-1)?.body).toEqual({ words: ["", "a", "aa"] });
    expect(store.getState().batch?.map((r) => r.accepted)).toEqual([
      true,
      false,
      true,
    ]);
    await store.getState().run("a");
    store.getState().open("sha256:other");
    expect(store.getState()).toMatchObject({
      trace: null,
      batch: null,
      history: [],
    });
  });
});
