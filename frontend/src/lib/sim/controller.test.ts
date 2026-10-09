import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAnimationController } from "./controller";
import {
  DURATIONS,
  type Scene,
  type StepRequest,
  type TraceStep,
  playStep,
} from "./timeline";

const STEP: TraceStep = {
  index: 2,
  symbol: "a",
  after: ["q1", "q3", "q4", "q5"],
  transitions: [
    ["q0", "a", "q1"],
    ["q2", "a", "q3"],
  ],
  epsilonLayers: [[["q1", "ε", "q4"]], [["q4", "ε", "q5"]]],
};

function request(change: Partial<StepRequest> = {}): StepRequest {
  return {
    step: STEP,
    previous: ["q0", "q2", "q6"],
    last: false,
    accepted: false,
    witness: false,
    speed: 1,
    instant: false,
    hold: false,
    ...change,
  };
}

/** A scene that records each call with the time it happened. */
function recorder() {
  const calls: { at: number; call: string }[] = [];
  const witness: number[] = [];
  const start = performance.now();
  const note = (call: string) =>
    calls.push({ at: performance.now() - start, call });
  const scene: Scene = {
    read: (index) => note(`read ${index}`),
    tokens: (edges) => {
      note(`tokens ${edges.map((e) => e.join("")).join(" ")}`);
      return { progress: () => undefined, clear: () => note("clear") };
    },
    ripple: (states) => note(`ripple ${states.join(" ")}`),
    settle: (index, active, dropped, instant) =>
      note(
        `settle ${index} {${active.join(",")}} -{${dropped.join(",")}}${instant ? " instant" : ""}`,
      ),
    verdict: (accepted) => note(`verdict ${accepted}`),
    witness: (progress) => witness.push(progress),
    interrupt: () => note("interrupt"),
  };
  const names = () => calls.map((entry) => entry.call);
  const at = (call: string) => calls.find((entry) => entry.call === call)?.at;
  return { scene, names, at, witness };
}

beforeEach(() => {
  vi.useFakeTimers({
    toFake: [
      "requestAnimationFrame",
      "cancelAnimationFrame",
      "performance",
      "setTimeout",
      "clearTimeout",
      "setInterval",
      "clearInterval",
    ],
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("step timeline", () => {
  it("runs read → move → each ε layer → settle, in order and on time", () => {
    const { scene, names, at } = recorder();
    const done = vi.fn();
    playStep(createAnimationController(), scene, request(), done);

    expect(names()).toEqual(["read 2"]);
    vi.advanceTimersByTime(2000);
    expect(names()).toEqual([
      "read 2",
      "tokens q0aq1 q2aq3",
      "clear",
      "tokens q1εq4",
      "clear",
      "ripple q4",
      "tokens q4εq5",
      "clear",
      "ripple q5",
      "settle 2 {q1,q3,q4,q5} -{q0,q2,q6}",
    ]);
    expect(done).toHaveBeenCalledOnce();

    const { read, move, epsilon, settle } = DURATIONS;
    // A phase starts on the first frame after its predecessor's time is up.
    const starts = [
      [at("tokens q0aq1 q2aq3"), read],
      [at("tokens q1εq4"), read + move],
      [at("tokens q4εq5"), read + move + epsilon],
      [at("settle 2 {q1,q3,q4,q5} -{q0,q2,q6}"), read + move + 2 * epsilon],
    ];
    for (const [actual, nominal] of starts) {
      expect(actual).toBeGreaterThanOrEqual(nominal ?? 0);
      expect(actual).toBeLessThan((nominal ?? 0) + 20);
    }
    expect(settle).toBeGreaterThan(0);
  });

  it("divides every duration by the speed", () => {
    const { scene, at } = recorder();
    playStep(createAnimationController(), scene, request({ speed: 2 }));
    vi.advanceTimersByTime(2000);
    const settleAt = at("settle 2 {q1,q3,q4,q5} -{q0,q2,q6}") ?? 0;
    const nominal =
      (DURATIONS.read + DURATIONS.move + 2 * DURATIONS.epsilon) / 2;
    expect(settleAt).toBeGreaterThanOrEqual(nominal);
    expect(settleAt).toBeLessThan(nominal + 20);
  });

  it("ends with the verdict and draws the witness on the last step", () => {
    const { scene, names, witness } = recorder();
    playStep(
      createAnimationController(),
      scene,
      request({ last: true, accepted: true, witness: true }),
    );
    vi.advanceTimersByTime(3000);
    expect(names().slice(-2)).toEqual([
      "settle 2 {q1,q3,q4,q5} -{q0,q2,q6}",
      "verdict true",
    ]);
    expect(witness.at(-1)).toBe(1);
    expect(witness.length).toBeGreaterThan(2);
  });
});

describe("cancellation", () => {
  it("stops the step in flight when the step changes", () => {
    const controller = createAnimationController();
    const { scene, names } = recorder();
    const firstDone = vi.fn();
    playStep(controller, scene, request(), firstDone);
    vi.advanceTimersByTime(300);
    expect(names().at(-1)).toBe("tokens q0aq1 q2aq3");

    playStep(controller, scene, request({ step: { ...STEP, index: 3 } }));
    expect(names().slice(-2)).toEqual(["interrupt", "read 3"]);
    vi.advanceTimersByTime(3000);

    expect(firstDone).not.toHaveBeenCalled();
    const settles = names().filter((name) => name.startsWith("settle"));
    expect(settles).toEqual(["settle 3 {q1,q3,q4,q5} -{q0,q2,q6}"]);
  });

  it("does nothing more after cancel", () => {
    const controller = createAnimationController();
    const { scene, names } = recorder();
    const done = vi.fn();
    playStep(controller, scene, request(), done);
    vi.advanceTimersByTime(250);
    controller.cancel();
    const seen = names();
    vi.advanceTimersByTime(3000);
    expect(names()).toEqual(seen);
    expect(seen.at(-1)).toBe("interrupt");
    expect(done).not.toHaveBeenCalled();
    expect(controller.running()).toBe(false);
  });
});

describe("reduced motion", () => {
  it("changes states instantly: no tokens, no ripples, no frames", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
    }));
    const { scene, names, witness } = recorder();
    const done = vi.fn();
    playStep(
      createAnimationController(),
      scene,
      request({ last: true, accepted: true, witness: true }),
      done,
    );

    expect(names()).toEqual([
      "read 2",
      "settle 2 {q1,q3,q4,q5} -{q0,q2,q6} instant",
      "verdict true",
    ]);
    expect(witness).toEqual([1]);
    expect(done).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("still paces playback with the hold between steps", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { scene } = recorder();
    const done = vi.fn();
    playStep(createAnimationController(), scene, request({ hold: true }), done);
    expect(done).not.toHaveBeenCalled();
    vi.advanceTimersByTime(DURATIONS.hold + 20);
    expect(done).toHaveBeenCalledOnce();
  });
});

it("never uses setInterval", () => {
  const setInterval = vi.spyOn(globalThis, "setInterval");
  const { scene } = recorder();
  const controller = createAnimationController();
  playStep(controller, scene, request({ hold: true, last: true }));
  vi.advanceTimersByTime(5000);
  expect(setInterval).not.toHaveBeenCalled();
});
