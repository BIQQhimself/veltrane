"use client";

import * as React from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
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
          className="trade-call"
        >
          <span className="flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-label">
            <ArrowUpRight className="h-4 w-4" aria-hidden /> Call
          </span>
          <span className="num text-2xl font-medium leading-none">+{payoutPct.toFixed(0)}%</span>
          <span className="text-3xs opacity-80">returns {money(stake + profit)}</span>
        </button>
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => onPick("put")}
          className="trade-put"
        >
          <span className="flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-label">
            <ArrowDownRight className="h-4 w-4" aria-hidden /> Put
          </span>
          <span className="num text-2xl font-medium leading-none">+{payoutPct.toFixed(0)}%</span>
          <span className="text-3xs opacity-80">loses {money(stake)} if wrong</span>
        </button>
      </div>
    </div>
  );
}
