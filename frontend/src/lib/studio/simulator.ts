import { createStore } from "zustand/vanilla";
import {
  type Api,
  type BatchResult,
  type Edge,
  type Problem,
  ProblemError,
  type SimulateResponse,
  type StepModel,
  edge,
  settle,
} from "@/lib/api/client";
import type { TraceStep } from "@/lib/sim/timeline";

export const SPEEDS = [0.25, 0.5, 1, 1.5, 2, 4] as const;
// CLAUDE.md: above 500 symbols the animation changes states instantly.
export const LONG_WORD = 500;
// spec §11: limits.max_batch_size.
export const BATCH_LIMIT = 100;
const HISTORY_LIMIT = 20;

export type Trace = {
  word: string;
  accepted: boolean;
  witness: Edge[] | null;
  total: number;
  pages: number;
  pageSize: number;
  /** Loaded pages of steps, by page number (1-based, spec §9.3). */
  steps: Record<number, TraceStep[]>;
};

/** How the position last changed: one step forward animates, anything else jumps. */
export type Motion = "forward" | "jump";

export type HistoryEntry = { word: string; accepted: boolean };

export type SimulatorState = {
  automatonId: string | null;
  word: string;
  trace: Trace | null;
  running: boolean;
  loadingPage: number | null;
  problem: Problem | null;
  position: number;
  motion: Motion;
  /** Bumped by every control change; the player restarts the step when it changes. */
  seq: number;
  playing: boolean;
  speed: number;
  showWitness: boolean;
  history: HistoryEntry[];
  /** What the animation has shown so far: written by the scene, read by the page. */
  head: number;
  settled: { index: number; active: string[] } | null;
  verdict: boolean | null;
  batchText: string;
  batch: BatchResult[] | null;
  batchRunning: boolean;
  batchProblem: Problem | null;
};

export type SimulatorActions = {
  open: (automatonId: string) => void;
  setWord: (word: string) => void;
  run: (word: string) => Promise<void>;
  stepForward: () => void;
  stepBack: () => void;
  toStart: () => void;
  toEnd: () => void;
  seek: (position: number) => void;
  togglePlay: () => void;
  /** Called by the player when a step has finished while playing. */
  advance: () => void;
  setSpeed: (speed: number) => void;
  setShowWitness: (show: boolean) => void;
  show: (
    shown: Partial<Pick<SimulatorState, "head" | "settled" | "verdict">>,
  ) => void;
  setBatchText: (text: string) => void;
  runBatch: (words: string[]) => Promise<void>;
};

export type Simulator = SimulatorState & SimulatorActions;

const FRESH = {
  word: "",
  trace: null,
  running: false,
  loadingPage: null,
  problem: null,
  position: 0,
  motion: "jump",
  playing: false,
  history: [],
  head: 0,
  settled: null,
  verdict: null,
  batchText: "",
  batch: null,
  batchRunning: false,
  batchProblem: null,
} satisfies Partial<SimulatorState>;

function toStep(step: StepModel): TraceStep {
  return {
    index: step.index,
    symbol: step.symbol,
    after: step.after,
    transitions: step.transitions.map(edge),
    epsilonLayers: step.epsilon_layers.map((layer) => layer.map(edge)),
  };
}

/** The step at a position, if its page has been loaded. */
export function stepAt(
  trace: Trace | null,
  position: number,
): TraceStep | undefined {
  if (!trace) {
    return undefined;
  }
  const page = Math.floor(position / trace.pageSize) + 1;
  return trace.steps[page]?.[position % trace.pageSize];
}

export function createSimulatorStore(api: Api) {
  return createStore<Simulator>()((set, get) => {
    let request = 0;

    function failure(error: unknown): Problem {
      if (error instanceof ProblemError) {
        return error.problem;
      }
      throw error;
    }

    function simulate(word: string, page: number): Promise<SimulateResponse> {
      const automatonId = get().automatonId ?? "";
      return settle(
        api.POST("/v1/automata/{automaton_id}/simulate", {
          params: { path: { automaton_id: automatonId } },
          body: { word, witness: true, page },
        }),
      );
    }

    async function loadPage(page: number): Promise<void> {
      const { trace, loadingPage } = get();
      if (!trace || trace.steps[page] || loadingPage === page) {
        return;
      }
      const mine = request;
      set({ loadingPage: page });
      try {
        const response = await simulate(trace.word, page);
        if (mine !== request) {
          return;
        }
        set((state) => ({
          loadingPage: null,
          trace: state.trace && {
            ...state.trace,
            steps: { ...state.trace.steps, [page]: response.steps.map(toStep) },
          },
        }));
      } catch (error) {
        if (mine === request) {
          set({ loadingPage: null, problem: failure(error), playing: false });
        }
      }
    }

    function go(position: number, motion: Motion, playing: boolean): void {
      const { trace, seq } = get();
      if (!trace) {
        return;
      }
      const clamped = Math.min(Math.max(position, 0), trace.total - 1);
      set({
        position: clamped,
        motion,
        playing,
        seq: seq + 1,
        verdict: null,
      });
      void loadPage(Math.floor(clamped / trace.pageSize) + 1);
    }

    function last(): number {
      return (get().trace?.total ?? 1) - 1;
    }

    return {
      automatonId: null,
      seq: 0,
      speed: 1,
      showWitness: true,
      ...FRESH,

      open: (automatonId) => {
        if (get().automatonId !== automatonId) {
          request += 1;
          set({ automatonId, ...FRESH });
        }
      },

      setWord: (word) => set({ word }),

      run: async (word) => {
        const mine = ++request;
        // The previous word's verdict must not stand in for this one's.
        set({ running: true, problem: null, playing: false, verdict: null });
        try {
          const response = await simulate(word, 1);
          if (mine !== request) {
            return;
          }
          const steps = response.steps.map(toStep);
          const trace: Trace = {
            word,
            accepted: response.accepted,
            witness: response.witness?.map(edge) ?? null,
            total: response.total_steps,
            pages: response.pages,
            pageSize: response.pages > 1 ? steps.length : response.total_steps,
            steps: { 1: steps },
          };
          set((state) => ({
            running: false,
            trace,
            position: 0,
            motion: "forward",
            playing: true,
            seq: state.seq + 1,
            head: 0,
            settled: null,
            verdict: null,
            history: [
              { word, accepted: response.accepted },
              ...state.history.filter((entry) => entry.word !== word),
            ].slice(0, HISTORY_LIMIT),
          }));
        } catch (error) {
          if (mine === request) {
            set({ running: false, problem: failure(error) });
          }
        }
      },

      stepForward: () => {
        if (get().position < last()) {
          go(get().position + 1, "forward", false);
        }
      },
      stepBack: () => go(get().position - 1, "jump", false),
      toStart: () => go(0, "jump", false),
      toEnd: () => go(last(), "jump", false),
      seek: (position) => go(position, "jump", false),

      togglePlay: () => {
        const { playing, position } = get();
        if (playing) {
          go(position, "jump", false);
        } else if (position >= last()) {
          go(0, "forward", true);
        } else {
          go(position + 1, "forward", true);
        }
      },

      advance: () => {
        const { playing, position } = get();
        if (!playing) {
          return;
        }
        if (position < last()) {
          go(position + 1, "forward", true);
        } else {
          set({ playing: false });
        }
      },

      setSpeed: (speed) => {
        set({ speed });
        go(get().position, "jump", get().playing);
      },

      setShowWitness: (showWitness) => {
        set({ showWitness });
        go(get().position, "jump", get().playing);
      },

      show: (shown) => set(shown),

      setBatchText: (batchText) => set({ batchText }),

      runBatch: async (words) => {
        const automatonId = get().automatonId ?? "";
        set({ batchRunning: true, batchProblem: null });
        try {
          const response = await settle(
            api.POST("/v1/automata/{automaton_id}/simulate/batch", {
              params: { path: { automaton_id: automatonId } },
              body: { words },
            }),
          );
          set({ batchRunning: false, batch: response.results });
        } catch (error) {
          set({ batchRunning: false, batchProblem: failure(error) });
        }
      },
    };
  });
}

export type SimulatorStore = ReturnType<typeof createSimulatorStore>;
