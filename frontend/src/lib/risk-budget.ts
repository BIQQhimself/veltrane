import { money } from "@/lib/format";

export type RiskBudgetEntry = {
  label: string;
  used: number;
  cap: number;
  used_pct: number;
  remaining: number;
  unit: string;
  state: "ok" | "warning" | "blocked";
};

export type RiskBudget = {
  state: "ok" | "warning" | "blocked";
  equity: number;
  exposure: number;
  realized_pnl_today: number;
  open_positions: number;
  budgets: RiskBudgetEntry[];
  blocked: string[];
  notice?: string;
};

export function budgetValue(entry: RiskBudgetEntry) {
  if (entry.unit === "usd") return `${money(entry.used)} / ${money(entry.cap)}`;
  if (entry.unit === "pct") return `${entry.used.toFixed(1)}% / ${entry.cap.toFixed(0)}%`;
  return `${Math.round(entry.used)} / ${Math.round(entry.cap)}`;
}

export const entryTone = {
  ok: "text-paper-muted",
  warning: "text-warn",
  blocked: "text-loss",
} as const;

export const barTone = {
  ok: "bg-gold-400",
  warning: "bg-warn",
  blocked: "bg-loss",
} as const;

/** Badge wording for the overall budget state. */
export function budgetLabel(budget: RiskBudget | null, halted: boolean) {
  if (halted) return "Halted";
  if (!budget) return "Within limits";
  if (budget.state === "blocked") return "Entries blocked";
  if (budget.state === "warning") return "Near a limit";
  return "Within limits";
}

export function budgetTone(budget: RiskBudget | null, halted: boolean): "gain" | "warn" | "loss" {
  if (halted) return "loss";
  if (!budget) return "gain";
  if (budget.state === "blocked") return "loss";
  return budget.state === "warning" ? "warn" : "gain";
}
