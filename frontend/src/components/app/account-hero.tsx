"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, ShieldCheck, Zap } from "lucide-react";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/badge";
import { AreaChart } from "@/components/charts";
import { money, signedMoney } from "@/lib/format";

type HeroProps = {
  planCode: string;
  equityLabel: string;
  equity: number | null;
  netPnl: number | null;
  curve: number[];
  openTrades: number;
  demoUsed: number;
  demoLimit: number;
  riskLabel: string;
  riskTone: "gain" | "loss" | "warn" | "neutral" | "info";
  simulated: boolean;
  onStartPaper?: () => void;
  paperReady: boolean;
};

/**
 * The first thing an account owner sees: what the account is worth, how it has moved, and
 * whether anything is limiting them. Numbers are labelled by mode — a simulated balance is
 * never presented as real money.
 */
export function AccountHero({
  planCode,
  equityLabel,
  equity,
  netPnl,
  curve,
  openTrades,
  demoUsed,
  demoLimit,
  riskLabel,
  riskTone,
  simulated,
  onStartPaper,
  paperReady,
}: HeroProps) {
  const last = curve.at(-1) ?? 0;
  const previous = curve.length > 1 ? (curve.at(-2) ?? 0) : 0;
  const change = curve.length > 1 ? last - previous : null;
  const changePct = previous !== 0 && change !== null ? (change / Math.abs(previous)) * 100 : null;

  return (
    <section className="panel relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 opacity-[0.55]">
        <div className="absolute -left-24 -top-32 h-64 w-64 rounded-full bg-champagne-500/[0.07] blur-3xl" />
        <div className="absolute -right-16 top-0 h-56 w-56 rounded-full bg-champagne-500/[0.05] blur-3xl" />
      </div>
      <div className="relative grid gap-4 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)] lg:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <p className="label">{equityLabel}</p>
            <Badge tone="neutral">{planCode}</Badge>
            {simulated ? <Badge tone="warn">Simulated</Badge> : <Badge tone="info">Live account</Badge>}
          </div>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-3">
            <p className="num text-[34px] font-medium leading-none tracking-tight text-paper sm:text-[44px]">
              {equity == null ? "—" : money(equity)}
            </p>
            {change !== null ? (
              <p className={cn("num text-xs", change >= 0 ? "text-gain" : "text-loss")}>
                {change >= 0 ? "▲" : "▼"} {signedMoney(change)}
                {changePct !== null ? ` (${changePct.toFixed(2)}%)` : ""} last session
              </p>
            ) : (
              <p className="text-2xs text-paper-faint">First session</p>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="chip">
              <Zap className="h-3 w-3" aria-hidden /> {openTrades} open
            </span>
            <span className="chip">
              {demoUsed} / {demoLimit} demo executions today
            </span>
            <span
              className={cn(
                "chip",
                riskTone === "loss" && "border-loss/40 text-loss",
                riskTone === "warn" && "border-warn/40 text-warn",
                riskTone === "gain" && "border-gain/40 text-gain",
              )}
            >
              <ShieldCheck className="h-3 w-3" aria-hidden /> {riskLabel}
            </span>
            <span className="chip">
              Realised net <span className="num text-paper">{netPnl == null ? "—" : signedMoney(netPnl)}</span>
            </span>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Link
              href="/app/terminal"
              className="cta-gold inline-flex items-center gap-1.5 rounded-full px-4 py-2.5 text-xs font-semibold transition"
            >
              Open terminal
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
            {paperReady ? null : (
              <button
                type="button"
                onClick={onStartPaper}
                className="rounded-full border border-line-strong px-4 py-2.5 text-xs text-paper transition hover:border-line-strong hover:bg-obsidian-700/60"
              >
                Start paper account
              </button>
            )}
            <Link
              href="/app/portfolio"
              className="rounded-full px-3 py-2.5 text-xs text-paper-muted transition hover:text-paper"
            >
              View portfolio →
            </Link>
          </div>
        </div>

        <div className="min-w-0">
          {curve.length >= 2 ? (
            <div className="rounded-xl border border-line-soft bg-obsidian-900/50 p-2">
              <AreaChart
                values={curve}
                height={116}
                tone={last >= 0 ? "gain" : "loss"}
                ariaLabel="Cumulative realised profit and loss"
                formatValue={signedMoney}
              />
              <p className="mt-1 px-1 text-3xs text-paper-faint">Cumulative realised P&amp;L after costs</p>
            </div>
          ) : (
            <div className="flex h-[148px] flex-col items-center justify-center rounded-xl border border-dashed border-line-soft px-4 text-center">
              <p className="text-2xs text-paper-muted">No settled trades yet</p>
              <p className="mt-1 text-3xs leading-relaxed text-paper-faint">
                The curve appears after your first settled contract. Simulated results are labelled
                wherever they appear.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
