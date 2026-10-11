import createClient from "openapi-fetch";
import type { Readable } from "openapi-typescript-helpers";
import type { components, paths } from "./schema";
import type { Wake } from "./wake";

// Response types exactly as openapi-fetch returns them. Its Readable<> maps every array
// to an array of its element type, so a JSON tuple such as a δ triple arrives as
// (string | string[])[]; `triple` and `edge` below restore the shape with a runtime check.
type Schemas = {
  [K in keyof components["schemas"]]: Readable<components["schemas"][K]>;
};

export type IRDocument = Schemas["IRDocument-Output"];
export type Assumption = Schemas["Assumption"];
export type InterpretResponse = Schemas["InterpretResponse"];
export type Question = Schemas["QuestionModel"];
export type AutomatonSummary = Schemas["AutomatonSummary"];
export type Verification = Schemas["VerificationModel"];
export type AutomatonDetail = Schemas["AutomatonDetail"];
export type TableModel = Schemas["TableModel"];
export type GraphModel = Schemas["GraphModel"];
export type GraphNode = Schemas["GraphNodeModel"];
export type GraphEdge = Schemas["GraphEdgeModel"];
export type LogEntry = Schemas["LogEntryModel"];
export type SimulateResponse = Schemas["SimulateResponse"];
export type StepModel = Schemas["StepModel"];
export type BatchResult = Schemas["BatchResult"];
type ErrorModel = Schemas["ErrorModel"];

/** A JSON triple [string, string, string[]], checked rather than cast. */
export function triple(
  entry: readonly (string | string[])[],
): [string, string, string[]] {
  const [first, second, third] = entry;
  if (
    typeof first === "string" &&
    typeof second === "string" &&
    Array.isArray(third)
  ) {
    return [first, second, third];
  }
  throw new Error(
    `Expected [string, string, string[]], got ${JSON.stringify(entry)}`,
  );
}

/** A transition [source, symbol, target]; ε moves carry the symbol "ε". */
export type Edge = readonly [string, string, string];

/** A JSON edge triple from a trace or witness, checked rather than cast. */
export function edge(entry: readonly string[]): Edge {
  if (entry.length === 3) {
    return [entry[0], entry[1], entry[2]];
  }
  throw new Error(
    `Expected [string, string, string], got ${JSON.stringify(entry)}`,
  );
}

export type Api = ReturnType<typeof createApi>;

// Set at build time when the API runs on another host: the browser then calls it
// directly, so the API sees each visitor's own address for its rate limit. Unset, the
// calls go to /v1 on this site and the Next.js rewrite forwards them.
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");

// The hosted backend sleeps when idle; while it starts, its proxy answers 502/503/504 or
// drops the connection. Six attempts five seconds apart cover a typical cold start.
export const RETRY = { attempts: 6, delayMs: 5000 };

const GATEWAY_STATUSES = new Set([502, 503, 504]);

export type RetryOptions = {
  attempts?: number;
  delayMs?: number;
  listener?: Pick<Wake, "retrying" | "settled">;
};

/** True for a proxy's gateway error; the API's own 504 (E_TIMEOUT) would only time out again. */
async function isGatewayError(response: Response): Promise<boolean> {
  if (!GATEWAY_STATUSES.has(response.status)) {
    return false;
  }
  const body: unknown = await response
    .clone()
    .json()
    .catch(() => null);
  return !isErrorBody(body);
}

/** `fetchImpl`, retried on gateway errors and network failures while the server wakes. */
export function retryingFetch(
  fetchImpl: typeof fetch,
  {
    attempts = RETRY.attempts,
    delayMs = RETRY.delayMs,
    listener,
  }: RetryOptions = {},
): typeof fetch {
  return async (input, init) => {
    // A body can be read once, so every attempt sends a fresh clone.
    const request = new Request(input, init);
    const key = {};
    try {
      for (let attempt = 1; ; attempt += 1) {
        const last = attempt >= attempts;
        try {
          const response = await fetchImpl(request.clone());
          if (last || !(await isGatewayError(response))) {
            return response;
          }
        } catch (error) {
          if (last) {
            throw error;
          }
        }
        listener?.retrying(key, attempt + 1);
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    } finally {
      listener?.settled(key);
    }
  };
}

/** Typed client for /v1, on NEXT_PUBLIC_API_URL or on this site. */
export function createApi(
  options: {
    baseUrl?: string;
    fetch?: typeof fetch;
    retry?: RetryOptions;
  } = {},
) {
  // JSON bodies are typed; the text formats (CSV, LaTeX, SVG, DOT) are read with parseAs.
  return createClient<paths, "application/json">({
    baseUrl: options.baseUrl ?? API_URL,
    fetch: retryingFetch(options.fetch ?? globalThis.fetch, options.retry),
  });
}

/** One unretried health check, so a sleeping server starts waking before the first real call. */
export function wakeServer(): void {
  createClient<paths>({ baseUrl: API_URL })
    .GET("/v1/health")
    .catch(() => undefined);
}

/** An API error as shown to the user: the server's message names reason and next action. */
export type Problem = ErrorModel & { status: number | null };

export class ProblemError extends Error {
  constructor(readonly problem: Problem) {
    super(problem.message);
  }
}

export const NETWORK_PROBLEM: Problem = {
  code: "E_NETWORK",
  message:
    "Could not reach the NFA Studio server. Try again in a minute; if you run it yourself, start the backend first (see the README).",
  detail: {},
  status: null,
};

function isErrorBody(value: unknown): value is { error: ErrorModel } {
  return typeof value === "object" && value !== null && "error" in value;
}

/** The data of a successful call; anything else becomes a ProblemError. */
export async function settle<
  R extends { data?: unknown; error?: unknown; response: Response },
>(call: Promise<R>): Promise<NonNullable<R["data"]>> {
  let result: R;
  try {
    result = await call;
  } catch {
    throw new ProblemError(NETWORK_PROBLEM);
  }
  if (result.data !== undefined && result.data !== null && result.response.ok) {
    return result.data;
  }
  const status = result.response.status;
  if (isErrorBody(result.error)) {
    throw new ProblemError({ ...result.error.error, status });
  }
  throw new ProblemError({
    code: "E_HTTP",
    message: `The server answered with HTTP ${status}. Try again; if it keeps failing, check the backend log.`,
    detail: {},
    status,
  });
}
