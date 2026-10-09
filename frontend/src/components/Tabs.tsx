"use client";

import clsx from "clsx";
import { type KeyboardEvent, type ReactNode, useRef, useState } from "react";

export type Tab = { id: string; title: string; content: ReactNode };

/**
 * WAI-ARIA tabs: arrow keys move between tabs, Home and End jump to the ends, and only
 * the active panel is rendered, so a tab fetches its data when it is first opened.
 */
export function Tabs({ tabs, label }: { tabs: readonly Tab[]; label: string }) {
  const [active, setActive] = useState(tabs[0].id);
  const buttons = useRef(new Map<string, HTMLButtonElement>());

  function select(index: number): void {
    const tab = tabs[(index + tabs.length) % tabs.length];
    setActive(tab.id);
    buttons.current.get(tab.id)?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const index = tabs.findIndex((tab) => tab.id === active);
    const moves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    if (event.key in moves) {
      event.preventDefault();
      select(moves[event.key]);
    }
  }

  const current = tabs.find((tab) => tab.id === active) ?? tabs[0];
  return (
    <div className="flex flex-col gap-4">
      <div
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
        className="flex gap-1 overflow-x-auto border-b border-border"
      >
        {tabs.map((tab) => {
          const selected = tab.id === current.id;
          return (
            <button
              key={tab.id}
              ref={(element) => {
                if (element) {
                  buttons.current.set(tab.id, element);
                }
              }}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(tab.id)}
              className={clsx(
                "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium",
                selected
                  ? "border-accent text-text"
                  : "border-transparent text-muted hover:text-text",
              )}
            >
              {tab.title}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`panel-${current.id}`}
        aria-labelledby={`tab-${current.id}`}
        tabIndex={0}
        className="rounded-md"
      >
        {current.content}
      </div>
    </div>
  );
}
