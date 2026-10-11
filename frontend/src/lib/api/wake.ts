import { createStore } from "zustand/vanilla";

/** Requests retrying while a sleeping server wakes, each with the attempt it is on. */
export type Wake = {
  attempts: ReadonlyMap<object, number>;
  retrying: (request: object, attempt: number) => void;
  settled: (request: object) => void;
};

export type WakeStore = ReturnType<typeof createWakeStore>;

export function createWakeStore() {
  return createStore<Wake>()((set) => ({
    attempts: new Map(),
    retrying: (request, attempt) =>
      set(({ attempts }) => ({
        attempts: new Map(attempts).set(request, attempt),
      })),
    settled: (request) =>
      set(({ attempts }) => {
        if (!attempts.has(request)) {
          return {};
        }
        const next = new Map(attempts);
        next.delete(request);
        return { attempts: next };
      }),
  }));
}

/** The attempt to show: the furthest along of the waiting requests, or null when none wait. */
export function wakeAttempt(wake: Wake): number | null {
  return wake.attempts.size > 0 ? Math.max(...wake.attempts.values()) : null;
}
