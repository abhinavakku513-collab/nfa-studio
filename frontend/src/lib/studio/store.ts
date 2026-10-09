import { createStore } from "zustand/vanilla";
import {
  type Api,
  type AutomatonSummary,
  type IRDocument,
  type InterpretResponse,
  type Problem,
  ProblemError,
  type Question,
  settle,
} from "@/lib/api/client";
import { type Path, formatSymbols, setAt, withAlphabet } from "./ir";

/** Where the user is in Describe → Confirm → Build (spec §12.1). */
export type Stage = "describe" | "asking" | "confirming" | "editing" | "built";
export type Busy = "interpret" | "answer" | "build" | null;
/** Which step a problem belongs to, so it is shown next to what caused it. */
export type ProblemStep = "describe" | "confirm" | "build";

export type StudioState = {
  text: string;
  alphabetOverride: string[] | null;
  stage: Stage;
  busy: Busy;
  sessionId: string | null;
  question: Question | null;
  partialIr: Record<string, unknown> | null;
  missing: string[];
  ir: IRDocument | null;
  confidence: number | null;
  rejected: string[];
  manualText: string;
  summary: AutomatonSummary | null;
  problem: Problem | null;
  problemStep: ProblemStep | null;
};

export type StudioActions = {
  setText: (text: string) => void;
  setAlphabetOverride: (symbols: string[] | null) => void;
  interpret: () => Promise<void>;
  answer: (optionId: string) => Promise<void>;
  editIr: (path: Path, value: unknown) => void;
  setAlphabet: (symbols: string[]) => void;
  setAccepted: (assumptionId: string, accepted: boolean) => void;
  openManual: () => void;
  setManualText: (text: string) => void;
  buildManual: () => Promise<void>;
  build: () => Promise<void>;
  loadIr: (ir: IRDocument) => void;
  dismissProblem: () => void;
};

export type Studio = StudioState & StudioActions;

const FRESH: StudioState = {
  text: "",
  alphabetOverride: null,
  stage: "describe",
  busy: null,
  sessionId: null,
  question: null,
  partialIr: null,
  missing: [],
  ir: null,
  confidence: null,
  rejected: [],
  manualText: "",
  summary: null,
  problem: null,
  problemStep: null,
};

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function createStudioStore(api: Api) {
  return createStore<Studio>()((set, get) => {
    function fail(error: unknown, step: ProblemStep): void {
      if (!(error instanceof ProblemError)) {
        throw error;
      }
      set({ problem: error.problem, problemStep: step, busy: null });
    }

    function receive(response: InterpretResponse): void {
      const base = {
        busy: null,
        confidence: response.confidence,
        summary: null,
      } as const;
      if (response.status === "ready" && response.ir) {
        const override = get().alphabetOverride;
        const ir = override ? withAlphabet(response.ir, override) : response.ir;
        set({
          ...base,
          stage: "confirming",
          ir,
          sessionId: null,
          question: null,
          rejected: [],
        });
      } else if (
        response.status === "clarification_required" &&
        response.question
      ) {
        set({
          ...base,
          stage: "asking",
          sessionId: response.session_id ?? null,
          question: response.question,
          partialIr: response.partial_ir ?? null,
        });
      } else {
        set({
          ...base,
          stage: "editing",
          sessionId: null,
          question: null,
          partialIr: response.partial_ir ?? null,
          missing: response.missing ?? [],
          manualText: pretty(response.partial_ir ?? {}),
        });
      }
    }

    async function construct(ir: unknown, step: ProblemStep): Promise<void> {
      set({ busy: "build", problem: null, problemStep: null, summary: null });
      try {
        const summary = await settle(
          api.POST("/v1/automata", { body: ir as IRDocument }),
        );
        set({ summary, busy: null, stage: "built" });
      } catch (error) {
        fail(error, step);
      }
    }

    return {
      ...FRESH,

      setText: (text) => set({ text }),

      setAlphabetOverride: (symbols) => set({ alphabetOverride: symbols }),

      interpret: async () => {
        const { text, alphabetOverride, sessionId } = get();
        // An alphabet chosen before reading is stated explicitly, unless the text has one.
        const sent =
          alphabetOverride && !text.includes("{")
            ? `${text.trim()} over ${formatSymbols(alphabetOverride)}`
            : text;
        set({ ...FRESH, text, alphabetOverride, busy: "interpret" });
        try {
          receive(
            await settle(
              api.POST("/v1/interpret", {
                body: { text: sent, session_id: sessionId },
              }),
            ),
          );
        } catch (error) {
          fail(error, "describe");
        }
      },

      answer: async (optionId) => {
        const { sessionId, question } = get();
        if (!sessionId || !question) {
          return;
        }
        set({ busy: "answer", problem: null, problemStep: null });
        try {
          receive(
            await settle(
              api.POST("/v1/interpret/{session_id}/answer", {
                params: { path: { session_id: sessionId } },
                body: { question_id: question.id, option_id: optionId },
              }),
            ),
          );
        } catch (error) {
          fail(error, "confirm");
        }
      },

      editIr: (path, value) => {
        const ir = get().ir;
        if (ir) {
          set({
            ir: setAt(ir, path, value),
            summary: null,
            stage: "confirming",
          });
        }
      },

      setAlphabet: (symbols) => {
        const ir = get().ir;
        if (ir) {
          set({
            ir: withAlphabet(ir, symbols),
            summary: null,
            stage: "confirming",
          });
        } else {
          set({ alphabetOverride: symbols.length > 0 ? symbols : null });
        }
      },

      setAccepted: (assumptionId, accepted) => {
        const rejected = get().rejected.filter((id) => id !== assumptionId);
        set({ rejected: accepted ? rejected : [...rejected, assumptionId] });
      },

      openManual: () => {
        const { ir, partialIr } = get();
        set({
          stage: "editing",
          manualText: pretty(ir ?? partialIr ?? {}),
          summary: null,
        });
      },

      setManualText: (manualText) => set({ manualText }),

      buildManual: async () => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(get().manualText);
        } catch (error) {
          set({
            problemStep: "build",
            problem: {
              code: "E_SCHEMA_INVALID",
              message: `The IR is not valid JSON (${(error as Error).message}). Fix the text and build again.`,
              detail: {},
              status: null,
            },
          });
          return;
        }
        await construct(parsed, "build");
      },

      build: async () => {
        const ir = get().ir;
        if (ir) {
          await construct(ir, "build");
        }
      },

      // IR from outside the interpreter, such as a refusal's regular alternative, may omit
      // the lists the panels read; the server fills in the same defaults.
      loadIr: (ir) =>
        set({
          ...FRESH,
          text: get().text,
          stage: "confirming",
          ir: {
            ...ir,
            assumptions: ir.assumptions ?? [],
            clarifications: ir.clarifications ?? [],
          },
        }),

      dismissProblem: () => set({ problem: null, problemStep: null }),
    };
  });
}

export type StudioStore = ReturnType<typeof createStudioStore>;
