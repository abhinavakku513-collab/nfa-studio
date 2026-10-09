"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect } from "react";
import { useExplore } from "@/lib/studio/context";
import { viewKey } from "@/lib/studio/explore";
import { download } from "@/lib/svg";
import { ErrorNotice } from "./ErrorNotice";
import { ExportButtons, ViewToggles } from "./ViewToggles";

// spec §10.1: → marks the start state, * the accepting ones, →* a state that is both.
const MARKER_NAMES: Record<string, string> = {
  "→": "start state",
  "*": "accepting state",
  "→*": "start and accepting state",
};

function Cell({ states }: { states: readonly string[] }) {
  return states.length === 0 ? (
    <span className="text-subtle">∅</span>
  ) : (
    <>{`{${states.join(", ")}}`}</>
  );
}

export function TableTab({
  id,
  hasEpsilon,
}: {
  id: string;
  hasEpsilon: boolean;
}) {
  const view = useExplore((explore) => explore.view);
  const key = viewKey(id, view);
  const entry = useExplore((explore) => explore.tables[key]);
  const loadTable = useExplore((explore) => explore.loadTable);
  const tableText = useExplore((explore) => explore.tableText);

  useEffect(() => {
    void loadTable(id);
  }, [id, key, loadTable]);

  const name = `nfa-${id.replace(/^sha256:/, "").slice(0, 12)}`;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <ViewToggles hasEpsilon={hasEpsilon} />
        {entry?.status === "ready" && (
          <ExportButtons
            options={[
              {
                label: "CSV",
                run: async () =>
                  download(
                    await tableText(id, "csv"),
                    `${name}.csv`,
                    "text/csv",
                  ),
              },
              {
                label: "Markdown",
                run: async () =>
                  download(
                    await tableText(id, "md"),
                    `${name}.md`,
                    "text/markdown",
                  ),
              },
              {
                label: "LaTeX",
                run: async () =>
                  download(
                    await tableText(id, "tex"),
                    `${name}.tex`,
                    "application/x-tex",
                  ),
              },
              {
                label: "JSON",
                run: async () =>
                  download(
                    JSON.stringify(entry.data, null, 2),
                    `${name}.json`,
                    "application/json",
                  ),
              },
            ]}
          />
        )}
      </div>

      {entry?.status === "failed" ? (
        <ErrorNotice problem={entry.problem} />
      ) : entry?.status === "ready" ? (
        <>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full border-collapse font-mono text-sm">
              <caption className="sr-only">
                Transition table
                {entry.data.eps_free ? " of the ε-free version" : ""}: one row
                per state, one column per symbol.
              </caption>
              <thead className="bg-surface-2 text-left">
                <tr>
                  <th scope="col" className="w-10 px-3 py-2">
                    <span className="sr-only">Marker</span>
                  </th>
                  <th scope="col" className="px-3 py-2 font-sans font-semibold">
                    State
                  </th>
                  {entry.data.columns.map((column) => (
                    <th
                      key={column}
                      scope="col"
                      className="px-3 py-2 font-semibold"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entry.data.rows.map((row) => (
                  <tr key={row.state} className="border-t border-border">
                    <td className="px-3 py-2 text-accent">
                      {row.marker && (
                        <abbr
                          title={MARKER_NAMES[row.marker]}
                          aria-label={MARKER_NAMES[row.marker]}
                          className="no-underline"
                        >
                          {row.marker}
                        </abbr>
                      )}
                    </td>
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      {row.state}
                    </th>
                    {row.cells.map((cell, i) => (
                      <td key={entry.data.columns[i]} className="px-3 py-2">
                        <Cell states={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-subtle">
            → start state · * accepting state · ∅ no transition
            {entry.data.hidden_dead_states.length > 0 &&
              ` · hidden dead states: ${entry.data.hidden_dead_states.join(", ")}`}
          </p>
        </>
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted">
          <LoaderCircle
            aria-hidden
            className="size-4 animate-spin motion-reduce:animate-none"
          />
          Loading the table…
        </p>
      )}
    </div>
  );
}
