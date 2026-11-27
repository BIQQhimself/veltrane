"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, Timer, Wallet } from "lucide-react";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/badge";
import type { BinaryContract, Connection } from "@/lib/types";
import { money } from "@/components/terminal/instrument-bar";

/**
 * Balance and account identity, always visible while trading. The figures come from
 * `/portfolio/overview`, which separates real funds from simulated balances — this chip never
 * merges the two, and labels a simulated balance as simulated.
 */
export function AccountChip({
  connections,
  balance,
  currency = "USD",
  simulated,
  equityLabel,
}: {
  connections: Connection[];
  balance: number;
  currency?: string;
  simulated: boolean;
  equityLabel: string;
}) {
  const active = connections.find((connection) => connection.provider === "deriv" && connection.status === "connected");
  const isVirtual = Boolean(active?.provider_meta?.is_virtual) || active?.provider_account_type === "demo";
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-2 rounded-full border border-line-soft bg-white/[0.03] py-1 pl-2.5 pr-2">
        <Wallet className="h-3.5 w-3.5 text-paper-faint" aria-hidden />
        <div className="leading-tight">
          <p className="text-[9px] uppercase tracking-label text-paper-faint">{equityLabel}</p>
          <p className="num text-[13px] text-paper">
            {balance.toLocaleString(undefined, { style: "currency", currency, maximumFractionDigits: 2 })}
          </p>
        </div>
        {simulated ? (
          <span className="rounded-full bg-warn/15 px-1.5 py-0.5 text-[9px] uppercase tracking-label text-warn">
            Sim
          </span>
        ) : null}
      </div>
      <Link
        href="/app/accounts"
        className="hidden items-center gap-1.5 rounded-full border border-line-soft px-3 py-2 text-3xs text-paper-muted transition hover:border-line-strong hover:text-paper sm:flex"
      >
        {active ? (
          <>
            <span className="h-1.5 w-1.5 rounded-full bg-gain" aria-hidden />
            {isVirtual ? "Deriv demo" : "Deriv live"}
          </>
        ) : (
          "Connect Deriv"
        )}
      </Link>
    </div>
  );
}

function remaining(expiresAt: string) {
  return Math.max(0, Math.round((new Date(expiresAt).getTime() - Date.now()) / 1000));
}

export function Countdown({ expiresAt }: { expiresAt: string }) {
  const [left, setLeft] = React.useState(() => remaining(expiresAt));
  React.useEffect(() => {
    setLeft(remaining(expiresAt));
    const timer = setInterval(() => setLeft(remaining(expiresAt)), 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);
  const minutes = Math.floor(left / 60);
  const seconds = left % 60;
  return (
    <span className={cn("num text-xs", left <= 10 ? "text-warn" : "text-paper")}>
      {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, { tone: "gain" | "loss" | "neutral" | "warn"; label: string }> = {
    open: { tone: "warn", label: "Open" },
    won: { tone: "gain", label: "Won" },
    lost: { tone: "loss", label: "Lost" },
    void: { tone: "neutral", label: "Void" },
    rejected: { tone: "loss", label: "Rejected" },
  };
  const entry = map[status] ?? { tone: "neutral" as const, label: status };
  return <Badge tone={entry.tone}>{entry.label}</Badge>;
}

type DockProps = {
  tab: "open" | "history";
  onTab: (tab: "open" | "history") => void;
  open: BinaryContract[];
  settled: BinaryContract[];
  summary?: { win_rate_pct: number | null; net_pnl: number; staked_total: number };
  onOpenContract: (contract: BinaryContract) => void;
  loading?: boolean;
};

/**
 * The trade dock under the chart: what is live now, and what already settled. Rows are
 * clickable because every trade must open its full record.
 */
export function PositionsDock({ tab, onTab, open, settled, summary, onOpenContract, loading }: DockProps) {
  const rows = tab === "open" ? open : settled;
  return (
    <section className="panel" aria-label="Trades">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft px-3 py-2">
        <div className="flex gap-1" role="tablist" aria-label="Trades">
          {(
            [
              ["open", `Active trades (${open.length})`],
              ["history", `History (${settled.length})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => onTab(key)}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-2xs transition",
                tab === key ? "bg-champagne-500/15 text-champagne-200" : "text-paper-faint hover:text-paper-muted",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {summary ? (
          <div className="flex items-center gap-4 text-2xs">
            <span className="text-paper-faint">
              Win rate <span className="num text-paper">{summary.win_rate_pct ?? "—"}%</span>
            </span>
            <span className="text-paper-faint">
              Net{" "}
              <span className={cn("num", summary.net_pnl >= 0 ? "text-gain" : "text-loss")}>
                {money(summary.net_pnl)}
              </span>
            </span>
            <span className="hidden text-paper-faint sm:inline">
              Staked <span className="num text-paper">{money(summary.staked_total)}</span>
            </span>
          </div>
        ) : null}
      </div>

      {loading && !rows.length ? (
        <div className="space-y-2 p-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="shimmer h-9 rounded-lg" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center px-4 py-8 text-center">
          <Timer className="h-5 w-5 text-paper-faint" aria-hidden />
          <p className="mt-2 text-xs text-paper-muted">
            {tab === "open" ? "No active trades" : "Nothing has settled yet"}
          </p>
          <p className="mt-1 max-w-sm text-3xs text-paper-faint">
            {tab === "open"
              ? "Pick a direction on the ticket. The stake is held until expiry and settled against the price at that moment."
              : "Settled trades appear here with their entry, exit and net result after costs."}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-line-soft">
          {rows.map((contract) => (
            <li key={contract.id}>
              <button
                type="button"
                onClick={() => onOpenContract(contract)}
                className="flex w-full flex-wrap items-center justify-between gap-3 px-3 py-2.5 text-left transition hover:bg-obsidian-800/50"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
                      contract.direction === "call"
                        ? "border-gain/40 bg-gain/10 text-gain"
                        : "border-loss/40 bg-loss/10 text-loss",
                    )}
                  >
                    {contract.direction === "call" ? (
                      <ArrowUpRight className="h-4 w-4" aria-hidden />
                    ) : (
                      <ArrowDownRight className="h-4 w-4" aria-hidden />
                    )}
                  </span>
                  <div className="min-w-0">
                    <p className="font-mono text-xs text-paper">{contract.symbol}</p>
                    <p className="truncate text-3xs text-paper-faint">
                      {contract.direction.toUpperCase()} · {money(contract.stake)} · {contract.payout_pct}% ·{" "}
                      {Math.round(contract.duration_seconds / 60)}m
                      {contract.is_demo ? " · simulated" : ""}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-3xs text-paper-faint">Entry</p>
                    <p className="num text-xs text-paper">{contract.entry_price.toFixed(4)}</p>
                  </div>
                  {contract.status === "open" ? (
                    <div className="text-right">
                      <p className="text-3xs text-paper-faint">Expires in</p>
                      <Countdown expiresAt={contract.expires_at} />
                    </div>
                  ) : (
                    <div className="text-right">
                      <p className="text-3xs text-paper-faint">Net</p>
                      <p className={cn("num text-xs", contract.net_pnl >= 0 ? "text-gain" : "text-loss")}>
                        {money(contract.net_pnl)}
                      </p>
                    </div>
                  )}
                  <StatusPill status={contract.status} />
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
