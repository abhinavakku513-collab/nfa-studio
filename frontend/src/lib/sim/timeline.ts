import type { Edge } from "@/lib/api/client";
import type { AnimationController, Phase } from "./controller";

/** One step of a trace, as the animation needs it (spec §9.2 plus CLAUDE.md C2). */
export type TraceStep = {
  index: number;
  symbol: string | null;
  after: readonly string[];
  transitions: readonly Edge[];
  epsilonLayers: readonly (readonly Edge[])[];
};

/** Tokens travelling one set of edges together; `progress` takes eased time 0 to 1. */
export type TokenRun = { progress: (t: number) => void; clear: () => void };

/**
 * What a step animation does to the page. The simulator implements it on the diagram,
 * the tape and the store; tests record the calls.
 */
export type Scene = {
  /** The tape head moves to slot `index` (0 is before the first symbol). */
  read: (index: number) => void;
  tokens: (edges: readonly Edge[]) => TokenRun;
  ripple: (states: readonly string[]) => void;
  settle: (
    index: number,
    active: readonly string[],
    dropped: readonly string[],
    instant: boolean,
  ) => void;
  verdict: (accepted: boolean, instant: boolean) => void;
  /** Draw the witness path up to `progress`, 0 to 1. */
  witness: (progress: number) => void;
  /** Remove tokens and effects left by a cancelled timeline. */
  interrupt: () => void;
};

// CLAUDE.md "Simulation animation": base durations at 1× speed.
export const DURATIONS = {
  read: 200,
  move: 450,
  epsilon: 250,
  settle: 200,
  verdict: 700,
  hold: 300,
} as const;

export type StepRequest = {
  step: TraceStep;
  /** The active set before this step; null for step 0 or when it is not loaded. */
  previous: readonly string[] | null;
  last: boolean;
  accepted: boolean;
  /** Draw the witness on the verdict (accepted words only). */
  witness: boolean;
  speed: number;
  /** No tokens, ripples or tweening: backward steps, scrubbing, long words. */
  instant: boolean;
  /** Pause after the step before playback moves on. */
  hold: boolean;
};

export function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

function tokenPhase(
  scene: Scene,
  name: string,
  edges: readonly Edge[],
  duration: number,
  onArrive?: () => void,
): Phase {
  let run: TokenRun | null = null;
  return {
    name,
    duration,
    enter: () => {
      run = scene.tokens(edges);
    },
    frame: (t) => run?.progress(easeInOut(t)),
    exit: () => {
      run?.clear();
      run = null;
      onArrive?.();
    },
  };
}

/** read → move → ε layers → settle → verdict (last step) → hold (while playing). */
export function stepPhases(
  scene: Scene,
  request: StepRequest,
  instant: boolean,
): Phase[] {
  const { step, speed } = request;
  const ms = (base: number) => (instant ? 0 : base / speed);
  const phases: Phase[] = [
    {
      name: "read",
      duration: step.index === 0 ? 0 : ms(DURATIONS.read),
      enter: () => scene.read(step.index),
    },
  ];
  if (!instant) {
    if (step.transitions.length > 0) {
      phases.push(
        tokenPhase(scene, "move", step.transitions, ms(DURATIONS.move)),
      );
    }
    step.epsilonLayers.forEach((layer, i) => {
      const reached = [...new Set(layer.map(([, , target]) => target))];
      phases.push(
        tokenPhase(
          scene,
          `epsilon-${i + 1}`,
          layer,
          ms(DURATIONS.epsilon),
          () => scene.ripple(reached),
        ),
      );
    });
  }
  const dropped = (request.previous ?? []).filter(
    (state) => !step.after.includes(state),
  );
  phases.push({
    name: "settle",
    duration: ms(DURATIONS.settle),
    enter: () => scene.settle(step.index, step.after, dropped, instant),
  });
  if (request.last) {
    phases.push({
      name: "verdict",
      duration: ms(DURATIONS.verdict),
      enter: () => scene.verdict(request.accepted, instant),
      frame: request.witness ? (t) => scene.witness(easeInOut(t)) : undefined,
    });
  }
  if (request.hold) {
    phases.push({ name: "hold", duration: DURATIONS.hold / speed });
  }
  return phases;
}

/** Animate one step, cancelling whatever the controller was running. */
export function playStep(
  controller: AnimationController,
  scene: Scene,
  request: StepRequest,
  onDone?: () => void,
): void {
  const instant = request.instant || controller.reducedMotion();
  controller.run({
    phases: stepPhases(scene, request, instant),
    onDone,
    onCancel: scene.interrupt,
  });
}
