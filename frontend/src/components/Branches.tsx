"use client";

import clsx from "clsx";
import { ChevronRight, CircleCheck, CircleX } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import type { BranchModel, BranchesResponse } from "@/lib/api/client";
import { useSimulator, useSimulatorStore } from "@/lib/studio/context";
import { branchStepAt } from "@/lib/studio/simulator";
import { labelDiagram, prefixIds, sanitizeSvg } from "@/lib/svg";
import { ErrorNotice } from "./ErrorNotice";
import { playbackKeys } from "./Simulator";
import { Tape } from "./sim/Tape";

type Combiner = "all" | "any";

const COMBINERS: Record<Combiner, { badge: string; rule: string }> = {
  all: { badge: "ALL must accept", rule: "every branch must accept" },
  any: { badge: "ANY accepts", rule: "one accepting branch is enough" },
};

function set(states: readonly string[]): string {
  return states.length === 0 ? "∅" : `{${states.join(", ")}}`;
}

function Verdict({ accepted }: { accepted: boolean }) {
  return (
    <span
      className={clsx(
        "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold",
        accepted
          ? "bg-accent-soft text-accent-strong"
          : "bg-danger-soft text-danger",
      )}
    >
      {accepted ? (
        <CircleCheck aria-hidden className="size-3.5" />
      ) : (
        <CircleX aria-hidden className="size-3.5" />
      )}
      {accepted ? "Accepts" : "Rejects"}
    </span>
  );
}

/**
 * One branch: its own small machine, its own active set lit by the shared clock, and
 * its own verdict once the word has been read.
 */
function Lane({
  lane,
  active,
  accepting,
  accepted,
}: {
  lane: BranchModel;
  active: readonly string[] | null;
  accepting: boolean | null;
  accepted: boolean | null;
}) {
  const drawing = useRef<HTMLDivElement>(null);
  const prefix = `lane${lane.index}-`;
  const markup = useMemo(
    () => prefixIds(labelDiagram(sanitizeSvg(lane.svg), lane.graph), prefix),
    [lane, prefix],
  );

  useEffect(() => {
    const document = drawing.current?.ownerDocument;
    for (const node of lane.graph.nodes) {
      document
        ?.getElementById(`${prefix}${node.id}`)
        ?.classList.toggle("is-active", active?.includes(node.name) ?? false);
    }
  }, [markup, lane, prefix, active]);

  const number = lane.index + 1;
  return (
    <section
      aria-label={`Branch ${number}: ${lane.label}`}
      className="flex min-w-0 flex-1 flex-col gap-2 rounded-md border border-border bg-surface p-3"
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span
          aria-hidden
          className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border-strong text-xs font-semibold text-muted"
        >
          {number}
        </span>
        <span
          className={clsx(
            "min-w-0 flex-1 text-sm font-medium",
            lane.negated && "font-semibold",
          )}
        >
          {lane.label}
        </span>
        {active !== null && (
          <span className="font-mono text-xs text-muted">
            {set(active)}
            {accepting && " · accepting"}
          </span>
        )}
        {accepted !== null && <Verdict accepted={accepted} />}
      </header>
      <div
        ref={drawing}
        className="diagram [&_svg]:h-auto [&_svg]:max-h-40 [&_svg]:w-full"
        // Sanitised in sanitizeSvg, as the main diagram is.
        dangerouslySetInnerHTML={{ __html: markup }}
      />
    </section>
  );
}

/**
 * For "any": the union's shared start state, drawn once at the top, with an ε-move
 * fanning into each branch. Decorative; the group's name says the same in words.
 */
function Fan({
  first,
  last,
  active,
}: {
  first: boolean;
  last: boolean;
  active: boolean;
}) {
  return (
    <div aria-hidden className="absolute inset-y-0 left-0 w-10">
      {first && (
        <span
          className={clsx(
            "absolute left-0.5 top-0 size-5 rounded-full border-2 transition-colors duration-200 motion-reduce:transition-none",
            active
              ? "border-accent-strong bg-accent"
              : "border-muted bg-surface",
          )}
        />
      )}
      <span
        className={clsx(
          "absolute left-[11px] w-0.5 bg-muted",
          first ? "top-5" : "-top-3",
          last ? "bottom-1/2" : "bottom-0",
        )}
      />
      <span className="absolute left-[11px] right-1.5 top-1/2 h-0.5 bg-muted" />
      <ChevronRight className="absolute -right-0.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
      <span className="absolute left-4 top-1/2 -translate-y-[130%] font-mono text-xs text-muted">
        ε
      </span>
    </div>
  );
}

/** The combiner at the end of the lanes; it lights up with the final verdict. */
function CombinerBadge({
  combiner,
  lanes,
  accepted,
  combined,
}: {
  combiner: Combiner;
  lanes: readonly BranchModel[];
  accepted: readonly boolean[] | null;
  combined: boolean | null;
}) {
  const { badge, rule } = COMBINERS[combiner];
  let text = "";
  if (combined !== null && accepted) {
    // Name the branches that decided it: a rejecting one for "all", an accepting one for "any".
    const deciding = lanes.filter(
      (_, i) => accepted[i] === (combiner === "any"),
    );
    const which = deciding
      .map((lane) => `branch ${lane.index + 1} (${lane.label})`)
      .join(", ");
    const reason =
      deciding.length === 0
        ? combiner === "all"
          ? "every branch accepts"
          : "no branch accepts"
        : `${which} ${combiner === "any" ? "accepts" : "rejects"}`;
    text = `Combined verdict: ${combined ? "accepted" : "rejected"}; ${rule}, and ${reason}.`;
  }
  return (
    <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
      <p role="status" className="min-h-5 flex-1 text-sm text-muted">
        {text}
      </p>
      <span
        className={clsx(
          "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm font-semibold transition-colors duration-200 motion-reduce:transition-none",
          combined === null
            ? "border-border-strong text-muted"
            : combined
              ? "border-accent bg-accent-soft text-accent-strong"
              : "sim-shake border-danger bg-danger-soft text-danger",
        )}
      >
        {combined === true && <CircleCheck aria-hidden className="size-4" />}
        {combined === false && <CircleX aria-hidden className="size-4" />}
        {badge}
      </span>
    </div>
  );
}

/**
 * The Branches view: one lane per top-level condition, all fed by one tape and stepped
 * by the simulator's clock, so play, step, scrub and speed move every lane together.
 */
export function Branches({ data }: { data: BranchesResponse }) {
  const store = useSimulatorStore();
  const trace = useSimulator((sim) => sim.trace);
  const position = useSimulator((sim) => sim.position);
  const head = useSimulator((sim) => sim.head);
  const speed = useSimulator((sim) => sim.speed);
  const settled = useSimulator((sim) => sim.settled);
  const verdict = useSimulator((sim) => sim.verdict);
  const branchTrace = useSimulator((sim) => sim.branchTrace);
  const branchProblem = useSimulator((sim) => sim.branchProblem);
  const loadBranches = useSimulator((sim) => sim.loadBranches);

  useEffect(() => {
    if (trace) {
      void loadBranches();
    }
  }, [trace, position, loadBranches]);

  const combiner: Combiner = data.combiner ?? "all";
  const current =
    trace && branchTrace?.word === trace.word ? branchTrace : null;
  const step = settled ? branchStepAt(current, settled.index) : undefined;
  const done = verdict !== null && current !== null;
  const fan = combiner === "any";
  const count = data.branches.length;

  return (
    <div onKeyDown={playbackKeys(store)} className="flex flex-col gap-3">
      {trace ? (
        <Tape word={trace.word} head={head} speed={speed} />
      ) : (
        <p className="rounded-md border border-dashed border-border-strong p-3 text-sm text-muted">
          Simulate a word below: every branch reads it from the same tape, one
          symbol at a time.
        </p>
      )}
      {branchProblem && <ErrorNotice problem={branchProblem} />}
      <div
        role="group"
        aria-label={`${count} branches; ${COMBINERS[combiner].rule}${
          fan ? ". A shared start state moves by ε into each branch" : ""
        }`}
        className="flex flex-col gap-3"
      >
        {data.branches.map((lane, i) => (
          <div key={lane.index} className={clsx("relative", fan && "pl-10")}>
            {fan && (
              <Fan
                first={i === 0}
                last={i === count - 1}
                active={trace !== null && settled?.index === 0}
              />
            )}
            <Lane
              lane={lane}
              active={step?.active[i] ?? null}
              accepting={step?.accepting[i] ?? null}
              accepted={done ? current.accepted[i] : null}
            />
          </div>
        ))}
      </div>
      <CombinerBadge
        combiner={combiner}
        lanes={data.branches}
        accepted={current?.accepted ?? null}
        combined={done ? current.combined : null}
      />
    </div>
  );
}
