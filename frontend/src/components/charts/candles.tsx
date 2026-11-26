"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

export type Candle = { ts: number; open: number; high: number; low: number; close: number; volume?: number };

type Props = {
  candles: Candle[];
  height?: number;
  entryPrice?: number | null;
  entryDirection?: "call" | "put" | null;
  livePrice?: number | null;
  className?: string;
  ariaLabel?: string;
  showVolume?: boolean;
};

const UP = "#10b981";
const DOWN = "#f2555f";

function fmtPrice(value: number) {
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  if (Math.abs(value) >= 10) return value.toFixed(2);
  if (Math.abs(value) >= 1) return value.toFixed(3);
  return value.toFixed(5);
}

/**
 * Vertical scale for the price plot. Markers (a live quote, a contract entry) are
 * only honoured when they sit within a sane band of the candles: a marker from a
 * different instrument would otherwise flatten the whole series into one line.
 */
export function priceScale(
  candles: Array<Pick<Candle, "high" | "low">>,
  markers: Array<number | null | undefined> = [],
): { min: number; max: number; lo: number; hi: number } {
  const prices = candles.flatMap((candle) => [candle.high, candle.low]).filter((value) => Number.isFinite(value));
  const candleMin = prices.length ? Math.min(...prices) : 0;
  const candleMax = prices.length ? Math.max(...prices) : 0;
  const inBand = (value: number | null | undefined): value is number =>
    typeof value === "number" &&
    Number.isFinite(value) &&
    value > 0 &&
    (!prices.length || (value >= candleMin * 0.5 && value <= candleMax * 1.5));
  for (const marker of markers) {
    if (inBand(marker)) prices.push(marker);
  }
  const min = prices.length ? Math.min(...prices) : 0;
  const max = prices.length ? Math.max(...prices) : 1;
  const pad = (max - min) * 0.08 || max * 0.002 || 1;
  return { min, max, lo: min - pad, hi: max + pad };
}

/**
 * Candlestick chart drawn as SVG geometry so it stays sharp and needs no canvas or
 * charting dependency. Includes a price rail, volume histogram and the entry marker
 * for an open contract.
 */
export function CandleChart({
  candles,
  height = 320,
  entryPrice,
  entryDirection,
  livePrice,
  className,
  ariaLabel = "Candlestick chart",
  showVolume = true,
}: Props) {
  const id = React.useId().replace(/[:]/g, "");
  const [hover, setHover] = React.useState<number | null>(null);
  const width = 900;
  const padRight = 62;
  const padLeft = 6;
  const padTop = 10;
  const volumeHeight = showVolume ? 46 : 0;
  const plotHeight = height - padTop - volumeHeight - 18;
  const plotWidth = width - padLeft - padRight;

  const visible = candles.slice(-120);
  const data = visible.length ? visible : [];
  const { lo, hi } = priceScale(data, [livePrice, entryPrice]);

  const y = (price: number) => padTop + (1 - (price - lo) / (hi - lo || 1)) * plotHeight;
  const step = data.length ? plotWidth / data.length : plotWidth;
  const bodyWidth = Math.max(1.6, Math.min(9, step * 0.62));
  const maxVolume = Math.max(...data.map((c) => c.volume ?? 0), 1);

  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  const hovered = hover !== null ? data[hover] : null;

  return (
    <figure className={cn("relative w-full", className)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full select-none"
        role="img"
        aria-label={ariaLabel}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={`fill-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(46,123,255,0.10)" />
            <stop offset="100%" stopColor="rgba(46,123,255,0)" />
          </linearGradient>
        </defs>

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={padLeft}
              x2={width - padRight}
              y1={y(tick)}
              y2={y(tick)}
              stroke="rgba(255,255,255,0.045)"
              strokeDasharray="2 6"
            />
            <text
              x={width - padRight + 8}
              y={y(tick) + 3.5}
              fill="#6a788b"
              fontSize="10"
              fontFamily="var(--font-mono), monospace"
            >
              {fmtPrice(tick)}
            </text>
          </g>
        ))}

        {data.map((candle, index) => {
          const x = padLeft + index * step + step / 2;
          const up = candle.close >= candle.open;
          const colour = up ? UP : DOWN;
          const bodyTop = y(Math.max(candle.open, candle.close));
          const bodyBottom = y(Math.min(candle.open, candle.close));
          const bodyHeight = Math.max(1, bodyBottom - bodyTop);
          const volHeight = ((candle.volume ?? 0) / maxVolume) * volumeHeight * 0.9;
          return (
            <g key={candle.ts} onMouseEnter={() => setHover(index)}>
              <rect x={padLeft + index * step} y={padTop} width={step} height={plotHeight} fill="transparent" />
              <line
                x1={x}
                x2={x}
                y1={y(candle.high)}
                y2={y(candle.low)}
                stroke={colour}
                strokeWidth={1}
                opacity={0.9}
              />
              <rect
                x={x - bodyWidth / 2}
                y={bodyTop}
                width={bodyWidth}
                height={bodyHeight}
                fill={up ? colour : "transparent"}
                stroke={colour}
                strokeWidth={1}
                rx={0.6}
              />
              {showVolume ? (
                <rect
                  x={x - bodyWidth / 2}
                  y={height - 18 - volHeight}
                  width={bodyWidth}
                  height={volHeight}
                  fill={colour}
                  opacity={0.28}
                />
              ) : null}
            </g>
          );
        })}

        {entryPrice ? (
          <g>
            <line
              x1={padLeft}
              x2={width - padRight}
              y1={y(entryPrice)}
              y2={y(entryPrice)}
              stroke={entryDirection === "put" ? DOWN : UP}
              strokeWidth={1.1}
              strokeDasharray="5 4"
              opacity={0.85}
            />
            <rect
              x={padLeft + 2}
              y={y(entryPrice) - 9}
              width={104}
              height={17}
              rx={3}
              fill={entryDirection === "put" ? "rgba(242,85,95,0.16)" : "rgba(16,185,129,0.16)"}
              stroke={entryDirection === "put" ? DOWN : UP}
              strokeOpacity={0.5}
            />
            <text
              x={padLeft + 8}
              y={y(entryPrice) + 3.5}
              fill={entryDirection === "put" ? DOWN : UP}
              fontSize="9.5"
              fontFamily="var(--font-mono), monospace"
            >
              ENTRY {fmtPrice(entryPrice)}
            </text>
          </g>
        ) : null}

        {livePrice ? (
          <g>
            <line
              x1={padLeft}
              x2={width - padRight}
              y1={y(livePrice)}
              y2={y(livePrice)}
              stroke="#5c9bff"
              strokeWidth={0.9}
              opacity={0.55}
            />
            <rect
              x={width - padRight + 2}
              y={y(livePrice) - 8}
              width={padRight - 6}
              height={16}
              rx={3}
              fill="#2e7bff"
            />
            <text
              x={width - padRight + 6}
              y={y(livePrice) + 3.5}
              fill="#fff"
              fontSize="9.5"
              fontFamily="var(--font-mono), monospace"
            >
              {fmtPrice(livePrice)}
            </text>
          </g>
        ) : null}

        {hovered ? (
          <g>
            <line
              x1={padLeft + (hover ?? 0) * step + step / 2}
              x2={padLeft + (hover ?? 0) * step + step / 2}
              y1={padTop}
              y2={padTop + plotHeight}
              stroke="rgba(255,255,255,0.16)"
              strokeDasharray="3 3"
            />
          </g>
        ) : null}
      </svg>

      {hovered ? (
        <div className="pointer-events-none absolute left-3 top-2 flex gap-3 rounded-md border border-line bg-obsidian-900/95 px-2.5 py-1.5 font-mono text-3xs text-paper-muted shadow-lift">
          <span>O {fmtPrice(hovered.open)}</span>
          <span>H {fmtPrice(hovered.high)}</span>
          <span>L {fmtPrice(hovered.low)}</span>
          <span className={hovered.close >= hovered.open ? "text-gain" : "text-loss"}>
            C {fmtPrice(hovered.close)}
          </span>
        </div>
      ) : null}
    </figure>
  );
}
