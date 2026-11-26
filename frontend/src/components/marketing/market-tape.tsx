"use client";

import * as React from "react";

type Row = { symbol: string; price: number; is_demo: boolean; asset_class: string };

/**
 * Public market tape. Reads the public /markets/summary endpoint and labels every
 * value as simulated when the feed is simulated. It never invents a price: if the
 * API is unreachable the strip says so instead of showing fake numbers.
 */
export function MarketTape() {
  const [rows, setRows] = React.useState<Row[] | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:12001";
        const response = await fetch(`${base}/api/v1/markets/summary`, { cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        const body = await response.json();
        if (!cancelled) setRows(body.markets ?? []);
      } catch {
        if (!cancelled) setFailed(true);
      }
    };
    void load();
    const timer = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (failed) {
    return (
      <div className="border-y border-line-soft bg-obsidian-900/60 px-4 py-2.5 text-center text-2xs text-paper-faint">
        Market feed unavailable from this client — nothing is being simulated in its place.
      </div>
    );
  }

  const items = (rows ?? []).slice(0, 12);
  const doubled = [...items, ...items];

  return (
    <div className="relative overflow-hidden border-y border-line-soft bg-obsidian-900/60">
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-obsidian-950 to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-obsidian-950 to-transparent" />
      <div className="flex w-max animate-ticker items-center gap-8 py-2.5">
        {(items.length ? doubled : Array.from({ length: 8 }, () => null)).map((row, index) =>
          row ? (
            <span key={`${row.symbol}-${index}`} className="flex items-center gap-2 whitespace-nowrap text-2xs">
              <span className="font-medium text-paper-muted">{row.symbol}</span>
              <span className="num text-paper">
                {row.price.toLocaleString(undefined, { maximumFractionDigits: row.price < 10 ? 4 : 2 })}
              </span>
              {row.is_demo ? (
                <span className="rounded border border-line-strong px-1 py-px text-3xs uppercase tracking-label text-paper-faint">
                  sim
                </span>
              ) : null}
            </span>
          ) : (
            <span key={index} className="h-3 w-32 animate-pulse rounded bg-obsidian-750" />
          ),
        )}
      </div>
    </div>
  );
}
