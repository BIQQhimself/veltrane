"use client";

import { Sparkline } from "@/components/charts";
import { Badge } from "@/components/ui/badge";

type Row = { symbol: string; name: string; price: number; change: number; series: number[] };

const ROWS: Row[] = [
  { symbol: "BTC/USDT", name: "Bitcoin", price: 68420.5, change: 1.24, series: [42, 45, 43, 48, 47, 52, 50, 55, 58, 56, 61] },
  { symbol: "ETH/USDT", name: "Ethereum", price: 3540.12, change: -0.62, series: [58, 56, 57, 53, 54, 51, 52, 49, 50, 47, 46] },
  { symbol: "SOL/USDT", name: "Solana", price: 172.44, change: 3.18, series: [30, 33, 31, 36, 40, 38, 44, 42, 47, 51, 55] },
  { symbol: "EUR/USD", name: "Euro / Dollar", price: 1.0862, change: 0.08, series: [50, 50.4, 50.1, 50.6, 50.3, 50.8, 51, 50.7, 51.2, 51, 51.3] },
  { symbol: "XAU/USD", name: "Gold", price: 2384.7, change: -0.21, series: [46, 47, 45, 46, 44, 45, 43, 44, 42, 43, 42] },
];

export function DemoTape() {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-line-soft px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-info opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-info" />
          </span>
          <span className="label">Market tape</span>
        </div>
        <Badge tone="info">Demo data</Badge>
      </div>
      <div className="divide-y divide-line-soft/70">
        {ROWS.map((row) => (
          <div key={row.symbol} className="flex items-center justify-between gap-4 px-5 py-3">
            <div className="min-w-0">
              <p className="num text-xs text-paper">{row.symbol}</p>
              <p className="truncate text-2xs text-paper-faint">{row.name}</p>
            </div>
            <Sparkline values={row.series} tone={row.change >= 0 ? "gain" : "loss"} />
            <div className="text-right">
              <p className="num text-xs text-paper">
                {row.price.toLocaleString(undefined, { maximumFractionDigits: row.price > 100 ? 1 : 4 })}
              </p>
              <p className={`num text-2xs ${row.change >= 0 ? "text-gain" : "text-loss"}`}>
                {row.change >= 0 ? "+" : ""}
                {row.change.toFixed(2)}%
              </p>
            </div>
          </div>
        ))}
      </div>
      <p className="border-t border-line-soft px-5 py-2.5 text-2xs text-paper-faint">
        Illustrative values, not a live feed. Connect an account to see your own venue data.
      </p>
    </div>
  );
}
