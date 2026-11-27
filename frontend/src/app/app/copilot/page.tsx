"use client";

import * as React from "react";
import Link from "next/link";
import { Brain, Info, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { BinaryAsset, CopilotRead } from "@/lib/types";

const TIMEFRAMES = ["5m", "15m", "1h", "4h"] as const;
const DURATIONS = [
  { seconds: 60, label: "1 minute" },
  { seconds: 300, label: "5 minutes" },
  { seconds: 900, label: "15 minutes" },
  { seconds: 3600, label: "1 hour" },
];

export default function CopilotPage() {
  const assets = useApi<{ assets: BinaryAsset[] }>((signal) => api("/binary/assets", { signal }));
  const [symbol, setSymbol] = React.useState("BTC/USDT");
  const [timeframe, setTimeframe] = React.useState<(typeof TIMEFRAMES)[number]>("15m");
  const [duration, setDuration] = React.useState(300);

  const read = useApi<CopilotRead>(
    (signal) =>
      api("/copilot/analyse", {
        method: "POST",
        body: { symbol, timeframe, duration_seconds: duration },
        signal,
      }),
    [symbol, timeframe, duration],
  );

  const biasTone = read.data?.bias === "call" ? "gain" : read.data?.bias === "put" ? "loss" : "neutral";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-xl font-semibold tracking-tight text-paper sm:text-2xl">Copilot</h1>
            <Badge tone="info">Deterministic</Badge>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-paper-faint">
            A transparent technical read of the instrument you are looking at: trend, momentum, range
            position and volatility, with the reasoning and the level that would prove it wrong. It does
            not place contracts and it does not predict prices.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => read.refetch()} loading={read.loading}>
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          Recompute
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
        <section className="panel">
          <div className="border-b border-line-soft px-4 py-3">
            <p className="label">Instrument</p>
            <select
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-line bg-obsidian-900 px-2 py-2 text-xs text-paper outline-none focus:border-champagne-500/60"
              aria-label="Instrument"
            >
              {(assets.data?.assets ?? []).map((asset) => (
                <option key={asset.symbol} value={asset.symbol}>
                  {asset.symbol} · {asset.name}
                </option>
              ))}
            </select>
            <p className="label mt-4">Timeframe</p>
            <div className="mt-1.5 grid grid-cols-4 gap-1 rounded-lg border border-line-soft bg-obsidian-900/60 p-1">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  className={cn(
                    "rounded px-1 py-1.5 text-3xs transition",
                    timeframe === tf ? "bg-champagne-500/15 text-champagne-600" : "text-paper-faint hover:text-paper-muted",
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
            <p className="label mt-4">Contract horizon</p>
            <div className="mt-1.5 space-y-1">
              {DURATIONS.map((option) => (
                <button
                  key={option.seconds}
                  type="button"
                  onClick={() => setDuration(option.seconds)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg border px-2.5 py-2 text-2xs transition",
                    duration === option.seconds
                      ? "border-champagne-500/40 bg-champagne-500/10 text-champagne-600"
                      : "border-line-soft text-paper-faint hover:border-line-strong hover:text-paper-muted",
                  )}
                >
                  {option.label}
                  {option.seconds <= 300 ? <span className="text-3xs text-warn">noise-weighted</span> : null}
                </button>
              ))}
            </div>
          </div>
          <p className="px-4 py-3 text-3xs leading-relaxed text-paper-faint">
            The horizon changes how much weight short-term noise receives. Short expiries are
            deliberately discounted.
          </p>
        </section>

        <section className="space-y-3">
          {read.error ? (
            <div className="panel p-6 text-sm text-paper-muted">{read.error}</div>
          ) : read.loading && !read.data ? (
            <div className="panel p-4">
              <div className="shimmer h-24 rounded-lg" />
              <div className="shimmer mt-3 h-40 rounded-lg" />
            </div>
          ) : read.data ? (
            <>
              <div className="panel overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm text-paper">{read.data.symbol}</span>
                    <Badge tone={biasTone}>{read.data.bias === "neutral" ? "No edge" : read.data.bias}</Badge>
                    <span className="text-3xs text-paper-faint">
                      {read.data.confidence}% confidence · {read.data.model}
                    </span>
                  </div>
                  <span className="text-3xs text-paper-faint">
                    {read.data.data.is_demo ? "Simulated candles" : "Provider candles"} ·{" "}
                    {new Date(read.data.generated_at).toLocaleTimeString()}
                  </span>
                </div>
                <div className="grid grid-cols-2 divide-x divide-line-soft sm:grid-cols-4">
                  {[
                    ["Price", read.data.price.toLocaleString(undefined, { maximumFractionDigits: 4 })],
                    ["Trend", read.data.trend],
                    ["Momentum", read.data.momentum],
                    ["RSI", read.data.rsi != null ? read.data.rsi.toFixed(1) : "—"],
                  ].map(([label, value]) => (
                    <div key={label} className="px-4 py-3">
                      <p className="text-3xs uppercase tracking-label text-paper-faint">{label}</p>
                      <p className="num mt-0.5 text-sm capitalize text-paper">{value}</p>
                    </div>
                  ))}
                </div>
                <div className="border-t border-line-soft px-4 py-3">
                  <p className="label mb-2">Reasoning</p>
                  <ul className="space-y-1.5">
                    {read.data.rationale.map((line) => (
                      <li key={line} className="flex gap-2 text-2xs leading-relaxed text-paper-muted">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-champagne-400" aria-hidden />
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="border-t border-line-soft bg-obsidian-900/50 px-4 py-3">
                  <p className="flex items-start gap-2 text-2xs text-warn">
                    <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                    Invalidation: {read.data.invalidation}
                  </p>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="panel p-4">
                  <p className="flex items-center gap-1.5 text-2xs text-paper-muted">
                    <Brain className="h-3.5 w-3.5 text-champagne-600" aria-hidden />
                    How to read this
                  </p>
                  <ul className="mt-2 space-y-1.5 text-3xs leading-relaxed text-paper-faint">
                    <li>· Confidence is a function of how many independent reads agree, capped at 85%.</li>
                    <li>· A neutral bias means the indicators disagree — that is information, not a gap.</li>
                    <li>· At 76% payout a correct call returns 0.76x the stake, so a coin-flip expectation is negative.</li>
                  </ul>
                </div>
                <div className="panel p-4">
                  <p className="flex items-center gap-1.5 text-2xs text-paper-muted">
                    <Info className="h-3.5 w-3.5 text-champagne-600" aria-hidden />
                    What this is not
                  </p>
                  <p className="mt-2 text-3xs leading-relaxed text-paper-faint">{read.data.disclaimer}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="chip">No execution</span>
                    <span className="chip">No predictions</span>
                    <span className="chip">No signals sold</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between rounded-xl border border-line-soft bg-obsidian-900/40 px-4 py-3">
                <p className="flex items-center gap-1.5 text-3xs text-paper-faint">
                  <Sparkles className="h-3 w-3" aria-hidden />
                  Want to act on this? The terminal requires your explicit click.
                </p>
                <Link href="/app/terminal" className="text-2xs text-champagne-600 hover:text-champagne-600">
                  Open terminal →
                </Link>
              </div>
            </>
          ) : null}
        </section>
      </div>
    </div>
  );
}
