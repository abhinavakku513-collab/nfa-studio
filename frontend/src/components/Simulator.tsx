"use client";

import clsx from "clsx";
import { CircleCheck, CircleX, LoaderCircle, RotateCcw } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect } from "react";
import type { Geometry } from "@/lib/sim/geometry";
import { badSymbol, parseWord, showWord } from "@/lib/sim/word";
import {
  useExplore,
  useSimulator,
  useSimulatorStore,
} from "@/lib/studio/context";
import { LONG_WORD, type SimulatorStore, stepAt } from "@/lib/studio/simulator";
import { ErrorNotice } from "./ErrorNotice";
import { Batch } from "./sim/Batch";
import { Controls } from "./sim/Controls";
import { Tape } from "./sim/Tape";
import { usePlayer, useScene } from "./sim/useScene";
import { Button, Switch } from "./ui";

const CONTEXT = 20;

function set(states: readonly string[]): string {
  return states.length === 0 ? "∅" : `{${states.join(", ")}}`;
}

function WordInput({ alphabet }: { alphabet: readonly string[] | null }) {
  const text = useSimulator((sim) => sim.word);
  const running = useSimulator((sim) => sim.running);
  const setWord = useSimulator((sim) => sim.setWord);
  const run = useSimulator((sim) => sim.run);
  const word = parseWord(text);
  const bad = alphabet ? badSymbol(word, alphabet) : null;
  const sigma = alphabet ? `Σ = {${alphabet.join(", ")}}` : "Σ";

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!bad && !running) {
      void run(word);
    }
  }

  const symbols = Array.from(word);
  const from = bad ? Math.max(0, bad.position - 1 - CONTEXT) : 0;
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor="sim-word" className="text-sm font-medium">
        Word to simulate
      </label>
      <div className="flex gap-2">
        <input
          id="sim-word"
          value={text}
          onChange={(event) => setWord(event.target.value)}
          aria-invalid={bad !== null}
          aria-describedby="sim-word-help"
          autoComplete="off"
          spellCheck={false}
          placeholder="ε"
          className={clsx(
            "min-w-0 flex-1 rounded-md border bg-surface px-3 py-2 font-mono text-sm",
            bad ? "border-danger" : "border-control-border",
          )}
        />
        <Button
          type="submit"
          variant="primary"
          disabled={bad !== null || running}
        >
          {running && (
            <LoaderCircle
              aria-hidden
              className="size-4 animate-spin motion-reduce:animate-none"
            />
          )}
          Simulate
        </Button>
      </div>
      <div id="sim-word-help" className="text-xs">
        {bad ? (
          <div className="flex flex-col gap-1 text-danger">
            <p>
              Position {bad.position}: “{bad.symbol}” is not in {sigma}. Use
              only these symbols.
            </p>
            <p aria-hidden className="font-mono text-sm text-text">
              {from > 0 && "…"}
              {symbols.slice(from, bad.position - 1).join("")}
              <mark className="rounded-sm bg-danger-soft px-0.5 text-danger underline decoration-2">
                {bad.symbol}
              </mark>
              {symbols.slice(bad.position, bad.position + CONTEXT).join("")}
              {bad.position + CONTEXT < symbols.length && "…"}
            </p>
          </div>
        ) : (
          <p className="text-muted">
            {sigma}. Leave it empty or type ε for the empty word; Enter runs it.
          </p>
        )}
      </div>
    </form>
  );
}

function Verdict() {
  const verdict = useSimulator((sim) => sim.verdict);
  const seq = useSimulator((sim) => sim.seq);
  if (verdict === null) {
    return <span className="h-8" />;
  }
  // The status line announces the verdict, so this output is not live as well.
  return (
    <output
      key={seq}
      aria-label="Verdict"
      aria-live="off"
      className={clsx(
        "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm font-semibold",
        verdict
          ? "bg-accent-soft text-accent-strong"
          : "sim-shake bg-danger-soft text-danger",
      )}
    >
      {verdict ? (
        <CircleCheck aria-hidden className="size-4" />
      ) : (
        <CircleX aria-hidden className="size-4" />
      )}
      {verdict ? "Accepted" : "Rejected"}
    </output>
  );
}

/** "Step 3: read a, active {q0, q1}", announced as each step settles. */
function Status() {
  const trace = useSimulator((sim) => sim.trace);
  const settled = useSimulator((sim) => sim.settled);
  const verdict = useSimulator((sim) => sim.verdict);
  let text = "";
  if (trace && settled) {
    const symbol = stepAt(trace, settled.index)?.symbol;
    const read = settled.index === 0 ? "start" : `read ${symbol ?? "?"}`;
    text = `Step ${settled.index}: ${read}, active ${set(settled.active)}`;
    if (verdict !== null) {
      text += verdict ? ". Accepted." : ". Rejected.";
    }
  }
  return (
    <p aria-live="polite" className="min-h-5 font-mono text-sm">
      {text}
    </p>
  );
}

function Pages() {
  const trace = useSimulator((sim) => sim.trace);
  const position = useSimulator((sim) => sim.position);
  const loadingPage = useSimulator((sim) => sim.loadingPage);
  if (!trace) {
    return null;
  }
  const long = trace.total - 1 > LONG_WORD;
  if (trace.pages <= 1 && !long) {
    return null;
  }
  const page = Math.floor(position / trace.pageSize) + 1;
  const first = (page - 1) * trace.pageSize;
  const last = Math.min(page * trace.pageSize, trace.total) - 1;
  return (
    <p className="flex items-center gap-2 text-xs text-muted">
      {trace.pages > 1 &&
        `Trace page ${page} of ${trace.pages} (steps ${first}–${last}). `}
      {long &&
        `The word is longer than ${LONG_WORD} symbols, so states change without tokens.`}
      {loadingPage !== null && (
        <span className="flex items-center gap-1">
          <LoaderCircle
            aria-hidden
            className="size-3 animate-spin motion-reduce:animate-none"
          />
          Loading steps…
        </span>
      )}
    </p>
  );
}

function History() {
  const history = useSimulator((sim) => sim.history);
  const running = useSimulator((sim) => sim.running);
  const setWord = useSimulator((sim) => sim.setWord);
  const run = useSimulator((sim) => sim.run);
  if (history.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby="history-title" className="flex flex-col gap-2">
      <h4 id="history-title" className="text-sm font-semibold">
        Tested words
      </h4>
      <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
        {history.map((entry) => (
          <li
            key={entry.word}
            className="flex items-center gap-3 px-3 py-1.5 text-sm"
          >
            {entry.accepted ? (
              <span className="flex w-24 items-center gap-1.5 text-accent">
                <CircleCheck aria-hidden className="size-4" />
                Accepted
              </span>
            ) : (
              <span className="flex w-24 items-center gap-1.5 text-danger">
                <CircleX aria-hidden className="size-4" />
                Rejected
              </span>
            )}
            <span className="min-w-0 flex-1 truncate font-mono">
              {showWord(entry.word)}
            </span>
            <Button
              variant="ghost"
              className="px-2 py-1 text-xs"
              disabled={running}
              aria-label={`Run ${showWord(entry.word)} again`}
              onClick={() => {
                setWord(showWord(entry.word));
                void run(entry.word);
              }}
            >
              <RotateCcw aria-hidden className="size-3.5" />
              Re-run
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Space, ←, →, Home, End drive playback anywhere in `store`'s views, except where they
 * type or select. Shared by the simulator and the Branches view's tape.
 */
export function playbackKeys(
  store: SimulatorStore,
): (event: KeyboardEvent<HTMLElement>) => void {
  return (event) => {
    const target = event.target as HTMLElement;
    const sim = store.getState();
    if (!sim.trace || target.closest("input, textarea, select, summary")) {
      return;
    }
    if (
      target.closest("button") &&
      (event.key === " " || event.key === "Enter")
    ) {
      return;
    }
    const actions: Record<string, () => void> = {
      " ": sim.togglePlay,
      ArrowLeft: sim.stepBack,
      ArrowRight: sim.stepForward,
      Home: sim.toStart,
      End: sim.toEnd,
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  };
}

/**
 * The simulator docked under the diagram (spec §12.1): type a word, watch the active
 * set move through the machine, step and scrub, and test many words at once. With
 * `tape` off, another view (the Branches lanes) shows the tape over its own drawing.
 */
export function Simulator({
  automatonId,
  geometry,
  idMap,
  accepting,
  note,
  tape = true,
}: {
  automatonId: string;
  geometry: Geometry | null;
  idMap: Readonly<Record<string, string>>;
  accepting: ReadonlySet<string>;
  note: string | null;
  tape?: boolean;
}) {
  const store = useSimulatorStore();
  const open = useSimulator((sim) => sim.open);
  const trace = useSimulator((sim) => sim.trace);
  const problem = useSimulator((sim) => sim.problem);
  const head = useSimulator((sim) => sim.head);
  const speed = useSimulator((sim) => sim.speed);
  const showWitness = useSimulator((sim) => sim.showWitness);
  const setShowWitness = useSimulator((sim) => sim.setShowWitness);
  const detail = useExplore((explore) => explore.details[automatonId]);
  const loadDetail = useExplore((explore) => explore.loadDetail);
  const { scene, layer } = useScene(geometry, idMap, accepting, store);
  usePlayer(scene, store);

  useEffect(() => {
    open(automatonId);
    void loadDetail(automatonId);
  }, [automatonId, open, loadDetail]);

  const alphabet =
    detail?.status === "ready" ? detail.data.five_tuple.Sigma : null;

  return (
    <section
      aria-labelledby="sim-title"
      onKeyDown={playbackKeys(store)}
      className="flex flex-col gap-4 border-t border-border pt-4"
    >
      <h3 id="sim-title" className="text-base font-semibold tracking-tight">
        Simulate
      </h3>
      {note && <p className="text-xs text-subtle">{note}</p>}
      <WordInput alphabet={alphabet} />
      {problem && <ErrorNotice problem={problem} />}
      {trace && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Verdict />
              <span className="truncate font-mono text-sm text-muted">
                {showWord(trace.word).slice(0, 40)}
                {trace.word.length > 40 && "…"}
              </span>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={showWitness}
                onChange={setShowWitness}
                label="Show witness path"
              />
              Show witness path
            </label>
          </div>
          {tape && <Tape word={trace.word} head={head} speed={speed} />}
          <Controls total={trace.total} />
          <Status />
          <Pages />
        </div>
      )}
      <History />
      <Batch />
      {layer}
    </section>
  );
}
