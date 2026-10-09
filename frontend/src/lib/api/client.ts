import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

type Schemas = components["schemas"];

export type IRDocument = Schemas["IRDocument-Output"];
export type IRNode = IRDocument["language"];
export type Assumption = Schemas["Assumption"];
export type InterpretResponse = Schemas["InterpretResponse"];
export type Question = Schemas["QuestionModel"];
export type AutomatonSummary = Schemas["AutomatonSummary"];
export type Verification = Schemas["VerificationModel"];
export type Capabilities = Schemas["Capabilities"];
type ErrorModel = Schemas["ErrorModel"];

export type Api = ReturnType<typeof createApi>;

/** Typed client for /v1; in the browser the Next.js rewrite forwards it to the backend. */
export function createApi(options: { baseUrl?: string; fetch?: typeof fetch } = {}) {
  return createClient<paths>({
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

/** The data of a successful call; anything else becomes a ProblemError. */
export async function settle<T>(
  call: Promise<{ data?: T; error?: { error: ErrorModel }; response: Response }>,
): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch {
    throw new ProblemError(NETWORK_PROBLEM);
  }
  if (result.data !== undefined && result.response.ok) {
    return result.data;
  }
  const status = result.response.status;
  if (result.error?.error) {
    throw new ProblemError({ ...result.error.error, status });
  }
  throw new ProblemError({
    code: "E_HTTP",
    message: `The server answered with HTTP ${status}. Try again; if it keeps failing, check the backend log.`,
    detail: {},
    status,
  });
}
