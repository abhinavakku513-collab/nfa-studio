"use client";

import {
  CircleCheck,
  CircleX,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";
import { useSimulator } from "@/lib/studio/context";
import { BATCH_LIMIT } from "@/lib/studio/simulator";
import { parseBatch, showWord } from "@/lib/sim/word";
import { ErrorNotice } from "../ErrorNotice";
import { Button } from "../ui";

/** Up to 100 words at once (spec §9): a results table, each row runnable on its own. */
export function Batch() {
  const text = useSimulator((sim) => sim.batchText);
  const results = useSimulator((sim) => sim.batch);
  const running = useSimulator((sim) => sim.batchRunning);
  const problem = useSimulator((sim) => sim.batchProblem);
  const setText = useSimulator((sim) => sim.setBatchText);
  const runBatch = useSimulator((sim) => sim.runBatch);
  const setWord = useSimulator((sim) => sim.setWord);
  const run = useSimulator((sim) => sim.run);

  const words = parseBatch(text);
  const tooMany = words.length > BATCH_LIMIT;
  const counts = results && {
    accepted: results.filter((r) => r.accepted === true).length,
    rejected: results.filter((r) => r.accepted === false).length,
    invalid: results.filter((r) => !r.valid).length,
  };

  return (
    <details className="rounded-md border border-border">
      <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">
        Batch test
      </summary>
      <div className="flex flex-col gap-3 border-t border-border p-3">
        <label htmlFor="batch-words" className="text-sm">
          Words, one per line (ε for the empty word, at most {BATCH_LIMIT})
        </label>
        <textarea
          id="batch-words"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={5}
          spellCheck={false}
          aria-invalid={tooMany}
          aria-describedby="batch-count"
          className="rounded-md border border-control-border bg-surface px-3 py-2 font-mono text-sm"
        />
        <div className="flex items-center justify-between gap-3">
          <p
            id="batch-count"
            className={tooMany ? "text-sm text-danger" : "text-xs text-muted"}
          >
            {tooMany
              ? `${words.length} words; the limit is ${BATCH_LIMIT}. Remove ${words.length - BATCH_LIMIT} or split the batch.`
              : `${words.length} ${words.length === 1 ? "word" : "words"}`}
          </p>
          <Button
            variant="secondary"
            disabled={words.length === 0 || tooMany || running}
            onClick={() => void runBatch(words)}
          >
            {running && (
              <LoaderCircle
                aria-hidden
                className="size-4 animate-spin motion-reduce:animate-none"
              />
            )}
            Run batch
          </Button>
        </div>
        {problem && <ErrorNotice problem={problem} />}
        {results && counts && (
          <>
            <p role="status" className="text-sm text-muted">
              {counts.accepted} accepted, {counts.rejected} rejected
              {counts.invalid > 0 && `, ${counts.invalid} invalid`}
            </p>
            <div className="max-h-72 overflow-auto rounded-md border border-border">
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">Batch results</caption>
                <thead className="sticky top-0 bg-surface-2 text-left">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-semibold">
                      Word
                    </th>
                    <th scope="col" className="px-3 py-2 font-semibold">
                      Result
                    </th>
                    <th scope="col" className="px-3 py-2">
                      <span className="sr-only">Action</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((result, i) => (
                    <tr key={i} className="border-t border-border">
                      <th
                        scope="row"
                        className="max-w-48 truncate px-3 py-2 text-left font-mono font-normal"
                      >
                        {showWord(result.word)}
                      </th>
                      <td className="px-3 py-2">
                        {!result.valid ? (
                          <span className="flex items-start gap-1.5 text-danger">
                            <TriangleAlert
                              aria-hidden
                              className="mt-0.5 size-4 shrink-0"
                            />
                            {result.error?.message ?? "Invalid word"}
                          </span>
                        ) : result.accepted ? (
                          <span className="flex items-center gap-1.5 text-accent">
                            <CircleCheck aria-hidden className="size-4" />
                            Accepted
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5 text-danger">
                            <CircleX aria-hidden className="size-4" />
                            Rejected
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {result.valid && (
                          <Button
                            variant="ghost"
                            className="px-2 py-1 text-xs"
                            aria-label={`Simulate ${showWord(result.word)}`}
                            onClick={() => {
                              setWord(showWord(result.word));
                              void run(result.word);
                            }}
                          >
                            Simulate
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </details>
  );
}
