import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-ink hover:bg-accent-strong disabled:bg-neutral-soft disabled:text-subtle",
  secondary:
    "border border-border-strong bg-surface text-text hover:bg-surface-2 disabled:text-subtle",
  ghost: "text-muted hover:bg-surface-2 hover:text-text disabled:text-subtle",
};

export function Button({
  variant = "secondary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
        "transition-colors disabled:cursor-not-allowed",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

/** One step of Describe → Confirm → Build: a numbered card whose number fills when done. */
export function StepCard({
  step,
  title,
  done = false,
  children,
  aside,
}: {
  step: number;
  title: string;
  done?: boolean;
  children: ReactNode;
  aside?: ReactNode;
}) {
  const id = `step-${step}-title`;
  return (
    <section
      aria-labelledby={id}
      className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6"
    >
      <header className="flex items-center gap-3">
        <span
          aria-hidden
          className={clsx(
            "flex size-6 items-center justify-center rounded-full text-xs font-semibold",
            done ? "bg-accent text-accent-ink" : "border border-border-strong text-muted",
          )}
        >
          {step}
        </span>
        <h2 id={id} className="text-base font-semibold tracking-tight">
          {title}
        </h2>
        {aside && <div className="ml-auto">{aside}</div>}
      </header>
      {children}
    </section>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-border-strong bg-surface-2 px-1 font-mono text-xs text-muted">
      {children}
    </kbd>
  );
}
