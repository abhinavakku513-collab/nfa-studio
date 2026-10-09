import { type Api, createApi } from "@/lib/api/client";

/** A JSON body, or `text` sent as `type` (SVG, DOT, CSV…). */
export type Reply =
  | { status?: number; json: unknown }
  | { status?: number; text: string; type: string };
export type Handler = (body: unknown, url: URL) => Reply | Promise<Reply>;

/**
 * A stand-in for the backend: "POST /v1/interpret" → handler, which also gets the URL
 * for its query string. Every request is recorded so a test can check what the page sent.
 */
export function fakeServer(routes: Record<string, Handler>) {
  const requests: { route: string; body: unknown }[] = [];
  const fetchImpl = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url);
    const route = `${request.method} ${decodeURIComponent(url.pathname)}`;
    const text = await request.text();
    const body: unknown = text ? JSON.parse(text) : null;
    requests.push({ route, body });
    const handler = routes[route];
    if (!handler) {
      return new Response(
        JSON.stringify({
          error: { code: "E_TEST", message: `no route ${route}`, detail: {} },
        }),
        {
          status: 404,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
    const reply = await handler(body, url);
    return "text" in reply
      ? new Response(reply.text, {
          status: reply.status ?? 200,
          headers: { "Content-Type": reply.type },
        })
      : new Response(JSON.stringify(reply.json), {
          status: reply.status ?? 200,
          headers: { "Content-Type": "application/json" },
        });
  };
  const api: Api = createApi({
    baseUrl: "http://studio.test",
    fetch: fetchImpl as typeof fetch,
  });
  return { api, requests };
}

export function problem(
  code: string,
  message: string,
  detail: Record<string, unknown> = {},
  status = 422,
): Reply {
  return { status, json: { error: { code, message, detail } } };
}

export const LIMITS = {
  max_nodes: 40,
  max_pattern_len: 16,
  max_count: 20,
  max_regex_len: 200,
  min_alphabet_size: 1,
  max_alphabet_size: 6,
  max_states: 200,
  time_budget_seconds: 2,
  max_word_len: 10000,
  trace_page_size: 200,
  max_batch_size: 100,
  max_text_len: 500,
  max_questions: 2,
  session_ttl_seconds: 1800,
  automaton_ttl_seconds: 1800,
  rate_limit_burst: 60,
  rate_limit_per_second: 1,
  render_timeout_seconds: 10,
  reference_max_states: 2000,
  bounded_max_words: 200000,
  bounded_max_length: 10,
  property_words: 500,
  property_max_length: 30,
};

export function ir(language: unknown, assumptions: unknown[] = []) {
  return {
    ir_version: "1.0",
    alphabet: { symbols: ["a", "b"], source: "inferred" },
    language,
    assumptions,
    clarifications: [],
    limits: LIMITS,
  };
}

export const READY = {
  status: "ready",
  confidence: 1,
  ir: ir({ type: "symbol_count", symbol: "a", op: "eq", n: 2 }, [
    {
      id: "alphabet_inferred",
      text: "The alphabet was inferred from the description.",
      editable: true,
    },
    {
      id: "zero_is_even",
      text: "Zero occurrences counts as even.",
      editable: false,
    },
  ]),
};

export const SUMMARY = {
  automaton_id: "sha256:abc123",
  kind: "dfa",
  state_count: 4,
  verification: {
    automaton_id: "sha256:abc123",
    level: "V2",
    badge: "green",
    checks: [
      { level: "V0", evidence: "Well-formed" },
      { level: "V1", evidence: "Verified on all strings up to length 10" },
      { level: "V2", evidence: "Exactly equivalent to reference" },
      { level: "V3", evidence: "Property tests passed (500 runs)" },
    ],
    bounded_length: 10,
    property_runs: 500,
    notes: [],
  },
  explanation: [
    {
      node: "symbol_count",
      text: "symbol_count a eq 2: one state per number of a seen.",
      states: 4,
    },
  ],
  assumptions: [],
  warnings: [],
};
