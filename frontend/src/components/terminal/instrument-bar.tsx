"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, ChevronDown, Search, Star } from "lucide-react";
import { cn } from "@/lib/cn";
import { CLASS_LABEL } from "@/lib/assets";
import type { BinaryAsset } from "@/lib/types";

export function fmtPrice(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Math.abs(value) >= 10) return value.toFixed(3);
  if (Math.abs(value) >= 1) return value.toFixed(4);
  return value.toFixed(5);
}

export function money(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

type InstrumentBarProps = {
  symbol: string;
  asset?: BinaryAsset;
  price: number;
  changePct: number;
  isDemoFeed: boolean;
  favourite: boolean;
  onToggleFavourite: () => void;
  onOpenPicker: () => void;
  onStep: (direction: -1 | 1) => void;
  /** Right-hand slot: balance and account summary. */
  children?: React.ReactNode;
};

/**
 * The band above the chart: which instrument, what it costs, and whose money is behind it.
 * Stepping through instruments keeps the eye on the chart instead of a long list.
 */
export function InstrumentBar({
  symbol,
  asset,
  price,
  changePct,
  isDemoFeed,
  favourite,
  onToggleFavourite,
  onOpenPicker,
  onStep,
  children,
}: InstrumentBarProps) {
  const up = changePct >= 0;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-obsidian-850/80 px-3 py-2.5 backdrop-blur">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onStep(-1)}
          aria-label="Previous instrument"
          className="rounded-lg border border-line-soft p-1.5 text-paper-faint transition hover:border-line-strong hover:text-paper"
        >
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
        </button>
        <button
          type="button"
          onClick={onOpenPicker}
          aria-label="Select instrument"
          className="group flex items-center gap-2 rounded-lg border border-line-soft bg-obsidian-900/70 px-3 py-1.5 transition hover:border-line-strong"
        >
          <span className="font-mono text-sm text-paper">{symbol}</span>
          <ChevronDown className="h-3.5 w-3.5 text-paper-faint transition group-hover:text-paper" aria-hidden />
        </button>
        <button
          type="button"
          onClick={() => onStep(1)}
          aria-label="Next instrument"
          className="rounded-lg border border-line-soft p-1.5 text-paper-faint transition hover:border-line-strong hover:text-paper"
        >
          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        </button>
        <button
          type="button"
          onClick={onToggleFavourite}
          aria-pressed={favourite}
          aria-label={favourite ? "Remove from watchlist" : "Add to watchlist"}
          className={cn(
            "ml-0.5 rounded-lg border p-1.5 transition",
            favourite
              ? "border-gold-400/50 bg-gold-400/10 text-gold-600"
              : "border-line-soft text-paper-faint hover:border-line-strong hover:text-paper",
          )}
        >
          <Star className={cn("h-3.5 w-3.5", favourite && "fill-current")} aria-hidden />
        </button>
      </div>

      <div className="flex min-w-0 items-baseline gap-2">
        <span className={cn("num text-xl font-medium tracking-tight", up ? "text-gain" : "text-loss")}>
          {fmtPrice(price)}
        </span>
        <span className={cn("num text-2xs", up ? "text-gain" : "text-loss")}>
          {up ? "▲" : "▼"} {Math.abs(changePct).toFixed(2)}%
        </span>
        <span className="hidden truncate text-3xs text-paper-faint sm:inline">
          {asset?.name ?? "—"} · {CLASS_LABEL[asset?.asset_class ?? ""] ?? "—"}
          {isDemoFeed ? " · simulated feed" : ""}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-2">{children}</div>
    </div>
  );
}

type WatchlistProps = {
  assets: BinaryAsset[];
  favourites: string[];
  active: string;
  onSelect: (symbol: string) => void;
  onToggleFavourite: (symbol: string) => void;
  loading?: boolean;
};

/**
 * The personal strip of instruments. Falls back to the first instruments on the book so a
 * new account still sees something useful before it has starred anything.
 */
export function Watchlist({ assets, favourites, active, onSelect, onToggleFavourite, loading }: WatchlistProps) {
  const rows = React.useMemo(() => {
    const starred = favourites
      .map((symbol) => assets.find((asset) => asset.symbol === symbol))
      .filter((asset): asset is BinaryAsset => Boolean(asset));
    if (starred.length) return starred;
    return assets.slice(0, 6);
  }, [assets, favourites]);

  if (loading && !assets.length) {
    return (
      <div className="flex gap-2 overflow-hidden">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="shimmer h-12 w-32 shrink-0 rounded-lg" />
        ))}
      </div>
    );
  }

  if (!rows.length) {
    return (
      <p className="rounded-lg border border-dashed border-line-soft px-3 py-3 text-2xs text-paper-faint">
        <Search className="mr-1.5 inline h-3 w-3" aria-hidden />
        No instruments are available right now.
      </p>
    );
  }

  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="list" aria-label="Watchlist">
      {rows.map((asset) => {
        const isActive = asset.symbol === active;
        const starred = favourites.includes(asset.symbol);
        return (
          <div
            key={asset.symbol}
            role="listitem"
            className={cn(
              "group flex shrink-0 items-center gap-1 rounded-lg border px-2 py-1.5 transition",
              isActive
                ? "border-champagne-500/50 bg-champagne-500/10"
                : "border-line-soft bg-obsidian-900/60 hover:border-line-strong",
            )}
          >
            <button type="button" onClick={() => onSelect(asset.symbol)} className="text-left">
              <span className="block font-mono text-2xs text-paper">{asset.symbol}</span>
              <span className="block text-3xs text-paper-faint">
                {CLASS_LABEL[asset.asset_class] ?? asset.asset_class}
              </span>
            </button>
            <button
              type="button"
              onClick={() => onToggleFavourite(asset.symbol)}
              aria-label={starred ? `Unstar ${asset.symbol}` : `Star ${asset.symbol}`}
              className={cn(
                "rounded p-1 transition",
                starred ? "text-gold-600" : "text-paper-faint/50 hover:text-paper-muted",
              )}
            >
              <Star className={cn("h-3 w-3", starred && "fill-current")} aria-hidden />
            </button>
          </div>
        );
      })}
    </div>
  );
}
