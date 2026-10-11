import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RETRY, createApi } from "@/lib/api/client";
import { createWakeStore } from "@/lib/api/wake";
import { StudioProvider } from "@/lib/studio/context";
import { createExploreStore } from "@/lib/studio/explore";
import { createSimulatorStore } from "@/lib/studio/simulator";
import { createStudioStore } from "@/lib/studio/store";
import { READY } from "@/test/fakeServer";
import { DescribeStep } from "./DescribeStep";
import { WakeNotice } from "./WakeNotice";

/** The page's stores on a server that answers 502 for its first `sleeping` requests. */
function sleepingServer(sleeping: number) {
  let calls = 0;
  const fetchImpl = async (): Promise<Response> => {
    calls += 1;
    return calls <= sleeping
      ? new Response("Bad Gateway", { status: 502 })
      : new Response(JSON.stringify(READY), {
          headers: { "Content-Type": "application/json" },
        });
  };
  const wake = createWakeStore();
  const api = createApi({
    baseUrl: "http://studio.test",
    fetch: fetchImpl,
    retry: { listener: wake.getState() },
  });
  return {
    studio: createStudioStore(api),
    explore: createExploreStore(api),
    simulator: createSimulatorStore(api),
    wake,
  };
}

async function read(stores: ReturnType<typeof sleepingServer>) {
  render(
    <StudioProvider stores={stores}>
      <WakeNotice />
      <DescribeStep />
    </StudioProvider>,
  );
  fireEvent.change(screen.getByLabelText(/describe a set of strings/i), {
    target: { value: "exactly two a's" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Read description" }));
  });
}

describe("WakeNotice", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a calm notice with the attempt while retrying, not an error", async () => {
    const stores = sleepingServer(2);
    await read(stores);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Waking up the server (free hosting sleeps when idle).",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      `Attempt 2 of ${RETRY.attempts}`,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(RETRY.delayMs));
    expect(screen.getByRole("status")).toHaveTextContent(
      `Attempt 3 of ${RETRY.attempts}`,
    );

    await act(() => vi.advanceTimersByTimeAsync(RETRY.delayMs));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(stores.studio.getState().stage).toBe("confirming");
  });

  it("shows the real error only after every attempt has failed", async () => {
    await read(sleepingServer(Infinity));
    await act(() =>
      vi.advanceTimersByTimeAsync(RETRY.delayMs * (RETRY.attempts - 2)),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      `Attempt ${RETRY.attempts} of ${RETRY.attempts}`,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(RETRY.delayMs));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    expect(screen.getByRole("alert")).toHaveTextContent("E_HTTP");
  });
});
