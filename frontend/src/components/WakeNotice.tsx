"use client";

import { LoaderCircle } from "lucide-react";
import { RETRY } from "@/lib/api/client";
import { wakeAttempt } from "@/lib/api/wake";
import { useWake } from "@/lib/studio/context";

/** Shown while requests retry against a sleeping server, in place of an error. */
export function WakeNotice() {
  const attempt = useWake(wakeAttempt);
  // The live region stays mounted so screen readers announce the notice when it appears.
  return (
    <div role="status" className="mx-auto max-w-7xl px-4 lg:px-8">
      {attempt !== null && (
        <div className="mt-6 flex gap-3 rounded-md border border-accent/40 bg-accent-soft p-4 text-sm">
          <LoaderCircle
            aria-hidden
            className="mt-0.5 size-4 shrink-0 animate-spin text-accent motion-reduce:animate-none"
          />
          <div className="flex flex-col gap-1">
            <p className="text-text">
              Waking up the server (free hosting sleeps when idle). This can
              take up to a minute…
            </p>
            <p className="text-xs text-muted">
              Attempt {attempt} of {RETRY.attempts}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
