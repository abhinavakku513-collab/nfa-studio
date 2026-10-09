/** One phase of a timeline; durations are already divided by the playback speed. */
export type Phase = {
  name: string;
  /** Milliseconds; 0 runs the phase within the frame that reaches it. */
  duration: number;
  enter?: () => void;
  /** Linear progress through the phase, 0 to 1; the phase applies its own easing. */
  frame?: (t: number) => void;
  exit?: () => void;
};

export type Timeline = {
  phases: readonly Phase[];
  onDone?: () => void;
  /** Called when a newer timeline or `cancel` stops this one before its end. */
  onCancel?: () => void;
};

/** Where time comes from; tests substitute fake timers through the globals. */
export type Clock = {
  now: () => number;
  requestFrame: (callback: () => void) => number;
  cancelFrame: (handle: number) => void;
  reducedMotion: () => boolean;
};

// Looked up on every call, so fake timers installed after import still apply.
const browserClock: Clock = {
  now: () => performance.now(),
  requestFrame: (callback) => requestAnimationFrame(() => callback()),
  cancelFrame: (handle) => cancelAnimationFrame(handle),
  reducedMotion: () =>
    typeof matchMedia === "function" &&
    matchMedia("(prefers-reduced-motion: reduce)").matches,
};

type Running = {
  timeline: Timeline;
  start: number;
  /** Index of the first phase that has not exited, and the time it starts at. */
  next: number;
  offset: number;
  entered: boolean;
  frame: number | null;
};

/**
 * The simulator's single animation clock: one requestAnimationFrame loop that runs one
 * timeline at a time. Starting a timeline cancels the one in flight, so any control
 * change stops the current animation at once. Phases run strictly in order; each is
 * entered, receives frames while its time lasts, and exits before the next one enters.
 * A timeline whose phases all take 0 ms completes synchronously inside `run`, without
 * requesting a frame. Playback is paced by phases too, never by setInterval.
 */
export function createAnimationController(clock: Clock = browserClock) {
  let current: Running | null = null;

  function tick(run: Running): void {
    run.frame = null;
    const { phases } = run.timeline;
    const elapsed = clock.now() - run.start;
    while (run.next < phases.length) {
      const phase = phases[run.next];
      if (!run.entered) {
        run.entered = true;
        phase.enter?.();
        if (current !== run) {
          return;
        }
      }
      const into = elapsed - run.offset;
      if (into < phase.duration) {
        phase.frame?.(into / phase.duration);
        break;
      }
      phase.frame?.(1);
      phase.exit?.();
      if (current !== run) {
        return;
      }
      run.offset += phase.duration;
      run.next += 1;
      run.entered = false;
    }
    if (run.next === phases.length) {
      current = null;
      run.timeline.onDone?.();
      return;
    }
    run.frame = clock.requestFrame(() => tick(run));
  }

  function cancel(): void {
    const run = current;
    if (!run) {
      return;
    }
    current = null;
    if (run.frame !== null) {
      clock.cancelFrame(run.frame);
    }
    run.timeline.onCancel?.();
  }

  function run(timeline: Timeline): void {
    cancel();
    const started: Running = {
      timeline,
      start: clock.now(),
      next: 0,
      offset: 0,
      entered: false,
      frame: null,
    };
    current = started;
    tick(started);
  }

  return {
    run,
    cancel,
    running: () => current !== null,
    reducedMotion: () => clock.reducedMotion(),
  };
}

export type AnimationController = ReturnType<typeof createAnimationController>;
