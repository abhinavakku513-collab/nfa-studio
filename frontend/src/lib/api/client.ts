import createClient from "openapi-fetch";
import type { Readable } from "openapi-typescript-helpers";
import type { components, paths } from "./schema";

// Response types exactly as openapi-fetch returns them. Its Readable<> maps every array
// to an array of its element type, so a JSON tuple such as a δ triple arrives as
// (string | string[])[]; `triple` below restores the shape with a runtime check.
type Schemas = {
  [K in keyof components["schemas"]]: Readable<components["schemas"][K]>;
};

export type IRDocument = Schemas["IRDocument-Output"];
export type IRNode = IRDocument["language"];
export type Assumption = Schemas["Assumption"];
export type InterpretResponse = Schemas["InterpretResponse"];
export type Question = Schemas["QuestionModel"];
export type AutomatonSummary = Schemas["AutomatonSummary"];
export type Verification = Schemas["VerificationModel"];
export type Capabilities = Schemas["Capabilities"];
export type AutomatonDetail = Schemas["AutomatonDetail"];
export type TableModel = Schemas["TableModel"];
export type GraphModel = Schemas["GraphModel"];
export type GraphNode = Schemas["GraphNodeModel"];
export type LogEntry = Schemas["LogEntryModel"];
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

export type Api = ReturnType<typeof createApi>;

/** Typed client for /v1; in the browser the Next.js rewrite forwards it to the backend. */
export function createApi(
  options: { baseUrl?: string; fetch?: typeof fetch } = {},
) {
  // JSON bodies are typed; the text formats (CSV, LaTeX, SVG, DOT) are read with parseAs.
  return createClient<paths, "application/json">({
    baseUrl: options.baseUrl ?? "",
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
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
    "Could not reach the NFA Studio server. Start the backend on port 8000 (see the README), then try again.",
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
