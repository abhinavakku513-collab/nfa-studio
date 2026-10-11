"use client";

import type { Api } from "@/lib/api/client";
import { StudioProvider } from "@/lib/studio/context";
import { BuildStep } from "./BuildStep";
import { ConfirmStep } from "./ConfirmStep";
import { DescribeStep } from "./DescribeStep";
import { Header } from "./Header";
import { Explore } from "./Explore";
import { WakeNotice } from "./WakeNotice";

/** The one page of spec §12.1: steps on the left, the automaton on the right. */
export function Studio({ api }: { api?: Api }) {
  return (
    <StudioProvider api={api}>
      <a
        href="#result"
        className="sr-only rounded-md bg-accent px-3 py-2 text-sm text-accent-ink focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10"
      >
        Skip to the automaton
      </a>
      <Header />
      <WakeNotice />
      <main className="mx-auto grid max-w-7xl items-start gap-6 px-4 py-6 lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)] lg:px-8">
        <div className="flex flex-col gap-4">
          <DescribeStep />
          <ConfirmStep />
          <BuildStep />
        </div>
        <Explore />
      </main>
    </StudioProvider>
  );
}
