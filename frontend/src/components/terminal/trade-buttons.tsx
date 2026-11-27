"use client";

import * as React from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { money } from "@/components/terminal/instrument-bar";

/**
 * The two decisions a fixed-odds trader makes: direction and size. Everything needed to judge
 * the trade — payout, profit if right, loss if wrong — is on the button itself, so nothing is
 * hidden behind a summary panel.
 */
export function TradeButtons({
  stake,
  payoutPct,
  durationLabel,
  disabled,
  busy,
  onPick,
}: {
  stake: number;
  payoutPct: number;
  durationLabel: string;
  disabled?: boolean;
  busy?: boolean;
  onPick: (direction: "call" | "put") => void;
}) {
  const profit = (stake * payoutPct) / 100;
  const common = "group relative flex flex-col items-center justify-center gap-1 rounded-xl border py-4 transition disabled:cursor-not-allowed disabled:opacity-50";
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between px-0.5">
        <p className="label">Place a trade</p>
        <p className="text-3xs text-paper-faint">
          {money(stake)} · {durationLabel} expiry
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => onPick("call")}
          className={cn(
            common,
            "border-gain/45 bg-gradient-to-b from-gain/25 to-gain/[0.06] text-gain hover:border-gain hover:from-gain/35",
          )}
        >
          <span className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-label">
            <ArrowUpRight className="h-4 w-4" aria-hidden /> Call
          </span>
          <span className="num text-lg font-medium leading-none">+{payoutPct.toFixed(0)}%</span>
          <span className="text-3xs text-gain/80">returns {money(stake + profit)}</span>
        </button>
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => onPick("put")}
          className={cn(
            common,
            "border-loss/45 bg-gradient-to-b from-loss/25 to-loss/[0.06] text-loss hover:border-loss hover:from-loss/35",
          )}
        >
          <span className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-label">
            <ArrowDownRight className="h-4 w-4" aria-hidden /> Put
          </span>
          <span className="num text-lg font-medium leading-none">+{payoutPct.toFixed(0)}%</span>
          <span className="text-3xs text-loss/80">loses {money(stake)} if wrong</span>
        </button>
      </div>
    </div>
  );
}
