"use client";

import { cn } from "@/lib/cn";
import { barTone, budgetValue, entryTone, type RiskBudget } from "@/lib/risk-budget";

/** Headroom left before the deterministic risk engine starts rejecting entries. */
export function RiskBudgetStrip({ budget }: { budget: RiskBudget | null }) {
  if (!budget) return null;
  const tone =
    budget.state === "blocked"
      ? "border-loss/40 bg-loss/[0.06]"
      : budget.state === "warning"
        ? "border-warn/40 bg-warn/[0.05]"
        : "border-line-soft";
  return (
    <section className={cn("rounded-xl border px-3 py-2.5", tone)} aria-label="Risk budget">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="text-3xs uppercase tracking-[0.14em] text-paper-faint">Risk budget</span>
        {budget.budgets.map((entry) => (
          <div key={entry.label} className="min-w-[118px] flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-3xs text-paper-faint">{entry.label}</span>
              <span className={cn("num text-3xs", entryTone[entry.state])}>{budgetValue(entry)}</span>
            </div>
            <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-ink-750" aria-hidden>
              <div
                className={cn("h-full rounded-full transition-[width] duration-500", barTone[entry.state])}
                style={{ width: `${Math.min(100, Math.max(1.5, entry.used_pct))}%` }}
              />
            </div>
          </div>
        ))}
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-3xs",
            budget.state === "blocked"
              ? "border-loss/40 text-loss"
              : budget.state === "warning"
                ? "border-warn/40 text-warn"
                : "border-gain/30 text-gain",
          )}
        >
          {budget.state === "blocked"
            ? `Entries blocked · ${budget.blocked.join(", ")}`
            : budget.state === "warning"
              ? "Close to a limit"
              : "Within limits"}
        </span>
      </div>
    </section>
  );
}

/** Vertical variant for the overview panel. */
export function RiskBudgetRows({ budget }: { budget: RiskBudget | null }) {
  if (!budget) {
    return <p className="text-2xs text-paper-faint">Risk budget unavailable. The engine still gates every order.</p>;
  }
  return (
    <div className="space-y-4">
      {budget.budgets.map((entry) => (
        <div key={entry.label}>
          <div className="flex items-baseline justify-between text-2xs">
            <span className="text-paper-faint">{entry.label}</span>
            <span className={cn("num", entryTone[entry.state])}>{budgetValue(entry)}</span>
          </div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-obsidian-750" aria-hidden>
            <div
              className={cn("h-full rounded-full transition-[width] duration-500", barTone[entry.state])}
              style={{ width: `${Math.min(100, Math.max(1.5, entry.used_pct))}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
