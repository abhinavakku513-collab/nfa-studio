import { createStore } from "zustand/vanilla";
import {
  type Api,
  type AutomatonDetail,
  type BranchesResponse,
  type GraphModel,
  type Problem,
  ProblemError,
  type TableModel,
  settle,
} from "@/lib/api/client";

export type Entry<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "failed"; problem: Problem };

/** Shared by the diagram and the table: the ε-free toggle and "show dead states". */
export type View = { epsFree: boolean; showDead: boolean };

type Cached = {
  details: AutomatonDetail;
  tables: TableModel;
  graphs: GraphModel;
  svgs: string;
  branches: BranchesResponse;
};

export type ExploreState = { view: View } & {
  [K in keyof Cached]: Record<string, Entry<Cached[K]>>;
};

export type ExploreActions = {
  setView: (change: Partial<View>) => void;
  loadDetail: (id: string) => Promise<void>;
  loadTable: (id: string) => Promise<void>;
  loadGraph: (id: string) => Promise<void>;
  loadSvg: (id: string) => Promise<void>;
  /** The Branches view's lanes; an automaton with one condition has none. */
  loadBranches: (id: string) => Promise<void>;
  tableText: (id: string, format: "csv" | "md" | "tex") => Promise<string>;
  dotText: (id: string) => Promise<string>;
};

export type Explore = ExploreState & ExploreActions;

/** Cache key of a view of one automaton. */
export function viewKey(id: string, view: View): string {
  return `${id}|${view.epsFree ? "eps-free" : "as-built"}|${view.showDead ? "dead" : "live"}`;
}

export function createExploreStore(api: Api) {
  return createStore<Explore>()((set, get) => {
    function put<K extends keyof Cached>(
      field: K,
      key: string,
      entry: Entry<Cached[K]>,
    ): void {
      set(
        (state) =>
          ({
            [field]: { ...state[field], [key]: entry },
          }) as Partial<ExploreState>,
      );
    }

    /** Fetch once per key; a failed fetch is tried again the next time it is asked for. */
    async function load<K extends keyof Cached>(
      field: K,
      key: string,
      fetcher: () => Promise<Cached[K]>,
    ): Promise<void> {
      const existing = get()[field][key];
      if (existing && existing.status !== "failed") {
        return;
      }
      put(field, key, { status: "loading" });
      try {
        put(field, key, { status: "ready", data: await fetcher() });
      } catch (error) {
        if (!(error instanceof ProblemError)) {
          throw error;
        }
        put(field, key, { status: "failed", problem: error.problem });
      }
    }

    function query() {
      const { epsFree, showDead } = get().view;
      return { eps_free: epsFree, show_dead: showDead };
    }

    return {
      view: { epsFree: false, showDead: false },
      details: {},
      tables: {},
      graphs: {},
      svgs: {},
      branches: {},

      setView: (change) =>
        set((state) => ({ view: { ...state.view, ...change } })),

      loadDetail: (id) =>
        load("details", id, () =>
          settle(
            api.GET("/v1/automata/{automaton_id}", {
              params: { path: { automaton_id: id } },
            }),
          ),
        ),

      loadTable: (id) =>
        load("tables", viewKey(id, get().view), () =>
          settle(
            api.GET("/v1/automata/{automaton_id}/table", {
              params: {
                path: { automaton_id: id },
                query: { format: "json", ...query() },
              },
            }),
          ),
        ),

      loadGraph: (id) =>
        load("graphs", viewKey(id, get().view), () =>
          settle(
            api.GET("/v1/automata/{automaton_id}/diagram", {
              params: {
                path: { automaton_id: id },
                query: { format: "json", ...query() },
              },
            }),
          ),
        ),

      loadSvg: (id) =>
        load("svgs", viewKey(id, get().view), () =>
          settle(
            api.GET("/v1/automata/{automaton_id}/diagram", {
              params: {
                path: { automaton_id: id },
                query: { format: "svg", ...query() },
              },
              parseAs: "text",
            }),
          ),
        ),

      loadBranches: (id) =>
        load("branches", id, () =>
          settle(
            api.GET("/v1/automata/{automaton_id}/branches", {
              params: { path: { automaton_id: id } },
            }),
          ),
        ),

      tableText: (id, format) =>
        settle(
          api.GET("/v1/automata/{automaton_id}/table", {
            params: {
              path: { automaton_id: id },
              query: { format, ...query() },
            },
            parseAs: "text",
          }),
        ),

      dotText: (id) =>
        settle(
          api.GET("/v1/automata/{automaton_id}/diagram", {
            params: {
              path: { automaton_id: id },
              query: { format: "dot", ...query() },
            },
            parseAs: "text",
          }),
        ),
    };
  });
}

export type ExploreStore = ReturnType<typeof createExploreStore>;
