"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";
import { type Theme, currentTheme, setTheme, subscribeTheme } from "@/lib/theme";

function ThemeToggle() {
  const theme = useSyncExternalStore<Theme>(subscribeTheme, currentTheme, () => "light");
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className="inline-flex size-9 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-text"
    >
      {theme === "dark" ? <Sun aria-hidden className="size-4" /> : <Moon aria-hidden className="size-4" />}
    </button>
  );
}

export function Header() {
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 lg:px-8">
        <span aria-hidden className="font-math text-lg text-accent">
          δ
        </span>
        <h1 className="text-lg font-semibold tracking-tight">NFA Studio</h1>
        <p className="hidden text-sm text-muted sm:block">
          Describe a language, confirm the reading, get a verified ε-NFA
        </p>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
