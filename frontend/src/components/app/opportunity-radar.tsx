"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Radar, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/cn";

/**
 * The ranked list the autonomous runner works from.
 *
 * Scores order candidates against each other. They are not win probabilities and the panel
 * says so once, in one line, instead of repeating a disclaimer under every row.
 */

type Opportunity = {
  symbol: string;
  sector: string;
  contract_type: "CALL" | "PUT";
  score: number;
  reason: string;
  indicators: { name?: string; rsi?: number; bars_since_cross?: number | null };
};

type Payload = {
  generated_at: string;
  scanned: number;
  qualifying: number;
  sector_cap: number;
  opportunities: Opportunity[];
  error?: string;
};

type Connection = { id: string; provider: string; status: string };

const SECTOR_LABEL: Record<string, string> = {
  synthetic_index: "Synthetics",
  forex: "Forex",
  commodities: "Commodities",
  cryptocurrency: "Crypto",
  indices: "Indices",
  stocks: "Stocks",
};

function sectorLabel(sector: string): string {
  return SECTOR_LABEL[sector] ?? sector.replace(/_/g, " ");
}

export function OpportunityRadar({ className }: { className?: string }) {
  const connections = useApi<{ connections: Connection[] }>((signal) => api("/connections", { signal }));
  const deriv = (connections.data?.connections ?? []).find(
    (item) => item.provider === "deriv" && item.status !== "revoked",
  );
  const [nonce, setNonce] = React.useState(0);

  const opportunities = useApi<Payload>(
    (signal) => api(`/deriv/connections/${deriv?.id}/opportunities`, { signal, query: { limit: 6 } }),
    [deriv?.id, nonce],
  );

  if (connections.loading) {
    return (
      <section className={cn("panel p-4 text-2xs text-paper-faint", className)} aria-busy>
        Reading markets…
      </section>
    );
  }

  if (!deriv) {
    return (
      <section className={cn("panel p-4", className)}>
        <Header onRefresh={null} />
        <p className="mt-3 text-2xs text-paper-muted">
          Connect a Deriv account to rank live markets.{" "}
          <Link href="/app/accounts" className="text-gold underline-offset-2 hover:underline">
            Connect
          </Link>
        </p>
      </section>
    );
  }

  const data = opportunities.data;
  const rows = data?.opportunities ?? [];

  return (
    <section className={cn("panel flex flex-col", className)}>
      <Header onRefresh={() => setNonce((value) => value + 1)} busy={opportunities.loading} />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line/60 px-4 py-2 text-3xs text-paper-faint">
        <span>
          {data ? `${data.scanned} markets scanned` : "Scanning…"}
        </span>
        <span>{data ? `${data.qualifying} above threshold` : "—"}</span>
        {data ? <span>max {data.sector_cap} per sector</span> : null}
        {data?.generated_at ? <span>updated {new Date(data.generated_at).toLocaleTimeString()}</span> : null}
      </div>

      {opportunities.error ? (
        <p className="px-4 py-3 text-2xs text-warn">{opportunities.error}</p>
      ) : rows.length === 0 ? (
        <div className="px-4 py-5">
          <p className="text-xs text-paper">Nothing qualifies right now</p>
          <p className="mt-1 text-2xs text-paper-faint">
            The scanner waits rather than lowering its threshold.
          </p>
        </div>
      ) : (
        <ul className="grid sm:grid-cols-2">
          {rows.map((row) => (
            <li key={row.symbol} className="flex items-center gap-3 border-b border-line/60 px-4 py-2.5">
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                  row.contract_type === "CALL" ? "bg-gain/12 text-gain" : "bg-loss/12 text-loss",
                )}
                aria-hidden
              >
                {row.contract_type === "CALL" ? (
                  <TrendingUp className="h-3.5 w-3.5" />
                ) : (
                  <TrendingDown className="h-3.5 w-3.5" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-paper">
                  {row.indicators?.name ?? row.symbol}
                  <span className="ml-2 text-3xs text-paper-faint">{sectorLabel(row.sector)}</span>
                </p>
                <p className="truncate text-3xs text-paper-faint">
                  {row.contract_type === "CALL" ? "Up" : "Down"} · RSI {row.indicators?.rsi ?? "—"}
                </p>
              </div>
              <div className="w-16 shrink-0">
                <div className="h-1 overflow-hidden rounded-full bg-line/70" aria-hidden>
                  <div
                    className={cn("h-full rounded-full", row.contract_type === "CALL" ? "bg-gain" : "bg-loss")}
                    style={{ width: `${Math.max(6, Math.min(100, row.score))}%` }}
                  />
                </div>
                <p className="mt-1 text-right text-3xs tabular-nums text-paper-muted">{row.score.toFixed(0)}</p>
              </div>
              <Link
                href={`/app/terminal?symbol=${encodeURIComponent(row.symbol)}`}
                className="shrink-0 rounded-md border border-line px-2 py-1 text-3xs text-paper-muted transition hover:border-gold/50 hover:text-gold"
                aria-label={`Trade ${row.symbol}`}
              >
                Trade
              </Link>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto flex items-center justify-between gap-3 border-t border-line/60 px-4 py-2">
        <p className="text-3xs text-paper-faint">Ranking only — not a probability or a return.</p>
        <Link
          href="/app/terminal"
          className="inline-flex items-center gap-1 text-2xs text-gold hover:underline"
        >
          Terminal
          <ArrowRight className="h-3 w-3" aria-hidden />
        </Link>
      </div>
    </section>
  );
}

function Header({ onRefresh, busy }: { onRefresh: (() => void) | null; busy?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 px-4 pt-3">
      <div className="flex items-center gap-2">
        <Radar className="h-3.5 w-3.5 text-gold" aria-hidden />
        <h2 className="text-xs font-medium tracking-wide text-paper">Opportunity radar</h2>
      </div>
      {onRefresh ? (
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-3xs text-paper-faint transition hover:text-paper"
          aria-label="Rescan markets"
        >
          <RefreshCw className={cn("h-3 w-3", busy && "animate-spin")} aria-hidden />
          Rescan
        </button>
      ) : null}
    </div>
  );
}
