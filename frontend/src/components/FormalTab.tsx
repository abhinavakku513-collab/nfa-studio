"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect } from "react";
import { triple } from "@/lib/api/client";
import { useExplore } from "@/lib/studio/context";
import { mathName, mathSet } from "@/lib/studio/math";
import { ErrorNotice } from "./ErrorNotice";

/** N = (Q, Σ, δ, q₀, F), typeset with the math font (spec §4). */
export function FormalTab({ id }: { id: string }) {
  const entry = useExplore((explore) => explore.details[id]);
  const loadDetail = useExplore((explore) => explore.loadDetail);

  useEffect(() => {
    void loadDetail(id);
  }, [id, loadDetail]);

  if (entry?.status === "failed") {
    return <ErrorNotice problem={entry.problem} />;
  }
  if (entry?.status !== "ready") {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <LoaderCircle
          aria-hidden
          className="size-4 animate-spin motion-reduce:animate-none"
        />
        Loading the definition…
      </p>
    );
  }

  const five = entry.data.five_tuple;
  const rows: [string, string][] = [
    ["Q", mathSet(five.Q)],
    ["Σ", `{${five.Sigma.join(", ")}}`],
    ["q₀", mathName(five.q0)],
    ["F", mathSet(five.F)],
  ];

  return (
    <div className="flex flex-col gap-4 font-math">
      <p className="text-base">
        N = (Q, Σ, δ, q₀, F){" "}
        <span className="font-sans text-sm text-muted">where</span>
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-base">
        {rows.map(([term, value]) => (
          <div key={term} className="contents">
            <dt>{term}</dt>
            <dd className="break-words">= {value}</dd>
          </div>
        ))}
      </dl>
      <section aria-labelledby="delta-title" className="flex flex-col gap-2">
        <h3 id="delta-title" className="font-sans text-sm font-semibold">
          δ, the transitions
        </h3>
        <ul className="grid gap-x-8 gap-y-1 text-base sm:grid-cols-2">
          {five.delta.map((entry) => {
            const [source, symbol, targets] = triple(entry);
            return (
              <li key={`${source} ${symbol}`}>
                δ({mathName(source)}, {symbol}) = {mathSet(targets)}
              </li>
            );
          })}
        </ul>
        <p className="font-sans text-xs text-subtle">
          Pairs not listed have no transition: δ(q, a) = ∅.
          {entry.data.dead.length > 0 &&
            ` Dead states (no accepting state is reachable from them): ${mathSet(entry.data.dead)}.`}
        </p>
      </section>
    </div>
  );
}
