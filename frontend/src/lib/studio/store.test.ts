import { describe, expect, it } from "vitest";
import { createApi } from "@/lib/api/client";
import { READY, SUMMARY, fakeServer, ir, problem } from "@/test/fakeServer";
import { createStudioStore } from "./store";

describe("studio store", () => {
  it("a ready reading moves to Confirm", async () => {
    const { api } = fakeServer({
      "POST /v1/interpret": () => ({ json: READY }),
    });
    const store = createStudioStore(api);
    store.getState().setText("exactly two a's");
    await store.getState().interpret();
    const state = store.getState();
    expect(state.stage).toBe("confirming");
    expect(state.ir?.language).toEqual({
      type: "symbol_count",
      symbol: "a",
      op: "eq",
      n: 2,
    });
    expect(state.busy).toBeNull();
  });

  it("a question is answered through its session", async () => {
    const { api, requests } = fakeServer({
      "POST /v1/interpret": () => ({
        json: {
          status: "clarification_required",
          code: "E_NEEDS_CLARIFICATION",
          session_id: "s_1",
          confidence: 1,
          question: {
            id: "Q1",
            topic: "overlap",
            text: "May the occurrences of aba overlap (as in ababa)?",
            options: [
              { id: "yes", label: "Yes, overlap allowed" },
              { id: "no", label: "No, they must be disjoint" },
              { id: "edit", label: "Edit manually" },
            ],
          },
          partial_ir: {
            alphabet: { symbols: ["a", "b"] },
            language: { type: "pattern_count", pattern: "aba" },
          },
        },
      }),
      "POST /v1/interpret/s_1/answer": () => ({ json: READY }),
    });
    const store = createStudioStore(api);
    store.getState().setText("contains aba twice");
    await store.getState().interpret();
    expect(store.getState().stage).toBe("asking");
    await store.getState().answer("yes");
    expect(requests[1]).toEqual({
      route: "POST /v1/interpret/s_1/answer",
      body: { question_id: "Q1", option_id: "yes" },
    });
    expect(store.getState().stage).toBe("confirming");
  });

  it("edit_ir opens the manual form with the partial IR", async () => {
    const partial = {
      alphabet: { symbols: ["a", "b"] },
      language: { type: "and", children: [] },
    };
    const { api } = fakeServer({
      "POST /v1/interpret": () => ({
        json: {
          status: "edit_ir",
          confidence: 1,
          partial_ir: partial,
          missing: ["overlap", "overlap", "grouping"],
        },
      }),
    });
    const store = createStudioStore(api);
    store.getState().setText("too many questions");
    await store.getState().interpret();
    expect(store.getState().stage).toBe("editing");
    expect(JSON.parse(store.getState().manualText)).toEqual(partial);
    expect(store.getState().missing).toHaveLength(3);
  });

  it("an alphabet chosen first is stated in the text and kept in the IR", async () => {
    const { api, requests } = fakeServer({
      "POST /v1/interpret": () => ({ json: READY }),
    });
    const store = createStudioStore(api);
    store.getState().setText("exactly two a's");
    store.getState().setAlphabet(["a", "b", "c"]);
    await store.getState().interpret();
    expect(requests[0].body).toEqual({
      text: "exactly two a's over {a, b, c}",
      session_id: null,
    });
    expect(store.getState().ir?.alphabet).toEqual({
      symbols: ["a", "b", "c"],
      source: "user",
    });
  });

  it("building returns the summary; editing afterwards clears it", async () => {
    const { api, requests } = fakeServer({
      "POST /v1/interpret": () => ({ json: READY }),
      "POST /v1/automata": () => ({ json: SUMMARY }),
    });
    const store = createStudioStore(api);
    store.getState().setText("exactly two a's");
    await store.getState().interpret();
    await store.getState().build();
    expect(store.getState().stage).toBe("built");
    expect(store.getState().summary?.verification.badge).toBe("green");
    expect(requests[1].body).toEqual(READY.ir);
    store.getState().editIr(["language", "n"], 3);
    expect(store.getState().summary).toBeNull();
    expect(store.getState().ir?.language).toMatchObject({ n: 3 });
  });

  it("a failed verification is kept with the build step", async () => {
    const { api } = fakeServer({
      "POST /v1/interpret": () => ({ json: READY }),
      "POST /v1/automata": () =>
        problem(
          "E_VERIFY_FAILED",
          "V1 failed: … The automaton is not shown.",
          { level: "V1", counterexample: "a" },
          500,
        ),
    });
    const store = createStudioStore(api);
    store.getState().setText("exactly two a's");
    await store.getState().interpret();
    await store.getState().build();
    const state = store.getState();
    expect(state.problemStep).toBe("build");
    expect(state.problem).toMatchObject({
      code: "E_VERIFY_FAILED",
      status: 500,
      detail: { counterexample: "a" },
    });
    expect(state.summary).toBeNull();
  });

  it("an unreachable server is a problem of its own", async () => {
    const api = createApi({
      baseUrl: "http://studio.test",
      fetch: (() =>
        Promise.reject(new TypeError("Failed to fetch"))) as typeof fetch,
    });
    const store = createStudioStore(api);
    store.getState().setText("anything");
    await store.getState().interpret();
    expect(store.getState().problem?.code).toBe("E_NETWORK");
    expect(store.getState().problem?.message).toMatch(
      /start the backend first/,
    );
  });

  it("manual IR that is not JSON is refused before it is sent", async () => {
    const { api, requests } = fakeServer({});
    const store = createStudioStore(api);
    store.getState().loadIr(ir({ type: "contains", pattern: "a" }) as never);
    store.getState().openManual();
    store.getState().setManualText("{ not json");
    await store.getState().buildManual();
    expect(store.getState().problem?.code).toBe("E_SCHEMA_INVALID");
    expect(requests).toHaveLength(0);
  });
});
