import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RETRY, createApi, settle } from "./client";
import { createWakeStore, wakeAttempt } from "./wake";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const HEALTHY = () => json(200, { status: "ok" });
const GATEWAY = () =>
  new Response("<html>502 Bad Gateway</html>", {
    status: 502,
    headers: { "Content-Type": "text/html" },
  });

/** A fetch that answers with `replies` in turn and records each request it was sent. */
function scripted(replies: (() => Response)[]) {
  const sent: Request[] = [];
  const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request;
    sent.push(request);
    const reply = replies[Math.min(sent.length, replies.length) - 1];
    return reply();
  });
  return { fetch: fetchImpl as unknown as typeof fetch, sent };
}

function health(fetchImpl: typeof fetch, wake = createWakeStore()) {
  const api = createApi({
    baseUrl: "http://studio.test",
    fetch: fetchImpl,
    retry: { listener: wake.getState() },
  });
  return settle(api.GET("/v1/health"));
}

describe("retrying while the server wakes", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("waits five seconds between attempts and succeeds once the server answers", async () => {
    const server = scripted([GATEWAY, GATEWAY, HEALTHY]);
    const wake = createWakeStore();
    const result = health(server.fetch, wake);

    await vi.advanceTimersByTimeAsync(0);
    expect(server.sent).toHaveLength(1);
    expect(wakeAttempt(wake.getState())).toBe(2);
    await vi.advanceTimersByTimeAsync(RETRY.delayMs - 1);
    expect(server.sent).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(server.sent).toHaveLength(2);
    expect(wakeAttempt(wake.getState())).toBe(3);
    await vi.advanceTimersByTimeAsync(RETRY.delayMs);

    await expect(result).resolves.toEqual({ status: "ok" });
    expect(server.sent).toHaveLength(3);
    expect(wakeAttempt(wake.getState())).toBeNull();
  });

  it.each([502, 503, 504])(
    "gives up after six attempts at HTTP %i and only then reports it",
    async (status) => {
      const server = scripted([() => new Response("", { status })]);
      const result = health(server.fetch);
      const settled = expect(result).rejects.toMatchObject({
        problem: { code: "E_HTTP", status },
      });
      await vi.runAllTimersAsync();
      await settled;
      expect(server.sent).toHaveLength(RETRY.attempts);
    },
  );

  it("retries a network failure and reports E_NETWORK when every attempt fails", async () => {
    const fetchImpl = vi.fn(() =>
      Promise.reject(new TypeError("Failed to fetch")),
    );
    const wake = createWakeStore();
    const result = health(fetchImpl as unknown as typeof fetch, wake);
    const settled = expect(result).rejects.toMatchObject({
      problem: { code: "E_NETWORK" },
    });
    await vi.runAllTimersAsync();
    await settled;
    expect(fetchImpl).toHaveBeenCalledTimes(RETRY.attempts);
    expect(wakeAttempt(wake.getState())).toBeNull();
  });

  it("sends the same body on every attempt", async () => {
    const server = scripted([GATEWAY, () => json(200, { ok: true })]);
    const api = createApi({
      baseUrl: "http://studio.test",
      fetch: server.fetch,
    });
    const result = api.POST("/v1/interpret", { body: { text: "ab" } });
    await vi.runAllTimersAsync();
    await result;
    const bodies = await Promise.all(server.sent.map((r) => r.text()));
    expect(bodies).toEqual([
      JSON.stringify({ text: "ab" }),
      JSON.stringify({ text: "ab" }),
    ]);
  });

  it("does not retry the API's own errors, including its 504 E_TIMEOUT", async () => {
    for (const reply of [
      () =>
        json(504, {
          error: { code: "E_TIMEOUT", message: "Too slow", detail: {} },
        }),
      () => new Response("", { status: 500 }),
      () =>
        json(429, {
          error: { code: "E_RATE_LIMITED", message: "", detail: {} },
        }),
    ]) {
      const server = scripted([reply]);
      const settled = expect(health(server.fetch)).rejects.toBeDefined();
      await vi.runAllTimersAsync();
      await settled;
      expect(server.sent).toHaveLength(1);
    }
  });
});
