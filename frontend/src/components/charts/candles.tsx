"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

export type Candle = {
  /** Epoch milliseconds. ISO strings from the API are accepted too. */
  ts: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type Drawing =
  | { id: string; type: "hline"; price: number }
  | { id: string; type: "trend"; from: { index: number; price: number }; to: { index: number; price: number } };

export type ChartMode = "candles" | "line";
export type DrawingTool = "none" | "hline" | "trend";

type Props = {
  candles: Candle[];
  height?: number;
  mode?: ChartMode;
  entryPrice?: number | null;
  entryDirection?: "call" | "put" | "buy" | "sell" | null;
  livePrice?: number | null;
  stopLoss?: number | null;
  takeProfit?: number | null;
  showVolume?: boolean;
  showEma?: boolean;
  showVwap?: boolean;
  showRsi?: boolean;
  showCrosshair?: boolean;
  drawings?: Drawing[];
  tool?: DrawingTool;
  onDraw?: (drawing: Drawing) => void;
  className?: string;
  ariaLabel?: string;
};

/** Shipped defaults. The rendered colours come from the runtime palette (see theme.ts). */
export const CHART_UP = "#0a7a4c";
export const CHART_DOWN = "#bd2643";
const UP = "rgb(var(--vt-chart-up))";
const DOWN = "rgb(var(--vt-chart-down))";
const GRID = "rgb(var(--vt-chart-grid))";
const AXIS_TEXT = "rgb(var(--vt-text-faint))";
const EMA_COLOR = "rgb(var(--vt-accent-400))";
const VWAP_COLOR = "rgb(var(--vt-chart-line-500))";

function fmtPrice(value: number) {
  if (!Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value) === 0 ? 0 : Math.floor(Math.log10(Math.abs(value)));
  const places = Math.min(8, Math.max(2, 5 - magnitude));
  return value.toLocaleString(undefined, {
    minimumFractionDigits: Math.min(2, places),
    maximumFractionDigits: places,
  });
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

/** Exponential moving average, seeded with the first close. */
export function ema(values: number[], period: number): number[] {
  if (!values.length || period < 1) return [];
  const k = 2 / (period + 1);
  const out: number[] = [values[0] as number];
  for (let i = 1; i < values.length; i += 1) {
    const value = values[i] as number;
    out.push(value * k + (out[i - 1] as number) * (1 - k));
  }
  return out;
}

/** Session VWAP from typical price and volume, carried forward from the first bar. */
export function vwap(candles: Candle[]): number[] {
  let pv = 0;
  let vol = 0;
  return candles.map((candle) => {
    const typical = (candle.high + candle.low + candle.close) / 3;
    const barVolume = candle.volume ?? 0;
    pv += typical * barVolume;
    vol += barVolume;
    return vol > 0 ? pv / vol : typical;
  });
}

/** A flat window has no average gain and no average loss, which is neutral (50). */
function rsiFrom(avgGain: number, avgLoss: number): number {
  if (avgLoss === 0) return avgGain === 0 ? 50 : 100;
  return 100 - 100 / (1 + avgGain / avgLoss);
}

/** Wilder-smoothed RSI. Returns null until the first full lookback window closes. */
export function rsi(values: number[], period = 14): Array<number | null> {
  if (values.length <= period) return values.map(() => null);
  const out: Array<number | null> = new Array(period).fill(null);
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i += 1) {
    const delta = (values[i] as number) - (values[i - 1] as number);
    if (delta >= 0) gain += delta;
    else loss -= delta;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out.push(rsiFrom(avgGain, avgLoss));
  for (let i = period + 1; i < values.length; i += 1) {
    const delta = (values[i] as number) - (values[i - 1] as number);
    avgGain = (avgGain * (period - 1) + Math.max(delta, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-delta, 0)) / period;
    out.push(rsiFrom(avgGain, avgLoss));
  }
  return out;
}

function ticks(lo: number, hi: number, count = 5) {
  const step = (hi - lo) / Math.max(1, count - 1);
  return Array.from({ length: count }, (_, i) => lo + step * i);
}

/**
 * Candlestick and line chart drawn as SVG so it stays sharp at any size and needs no
 * charting dependency. Includes a price rail, volume histogram, EMA overlay, live
 * quote, contract entry, stop-loss/take-profit bands, a crosshair readout and
 * click-to-draw horizontal and trend lines.
 */
export function CandleChart({
  candles,
  height = 340,
  mode = "candles",
  entryPrice = null,
  entryDirection = null,
  livePrice = null,
  stopLoss = null,
  takeProfit = null,
  showVolume = true,
  showEma = false,
  showVwap = false,
  showRsi = false,
  showCrosshair = true,
  drawings = [],
  tool = "none",
  onDraw,
  className,
  ariaLabel = "Price chart",
}: Props) {
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(880);
  const [hover, setHover] = React.useState<{ index: number; x: number; y: number } | null>(null);
  const [pending, setPending] = React.useState<{ index: number; price: number } | null>(null);

  React.useEffect(() => {
    const node = wrapRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width;
      if (next && Math.abs(next - width) > 1) setWidth(next);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [width]);

  const railWidth = 62;
  const padTop = 10;
  const axisHeight = 18;
  const panes = height - padTop - axisHeight;
  const volumeHeight = showVolume ? Math.round(panes * 0.16) : 0;
  const rsiHeight = showRsi ? Math.round(panes * 0.22) : 0;
  const plotHeight = Math.max(40, panes - volumeHeight - rsiHeight);
  const rsiTop = padTop + plotHeight + volumeHeight;
  const plotWidth = Math.max(60, width - railWidth);

  const { lo, hi } = priceScale(candles, [
    livePrice,
    entryPrice,
    stopLoss,
    takeProfit,
    ...drawings.flatMap((d) => (d.type === "hline" ? [d.price] : [d.from.price, d.to.price])),
  ]);
  const span = hi - lo || 1;
  // Axis precision follows the instrument's tick, not the zoom level: a EUR/USD
  // rail that rounds to 1.0911 hides the fifth decimal traders actually quote.
  const reference = livePrice ?? candles[candles.length - 1]?.close ?? hi;
  const tickDecimals = Math.min(6, Math.max(2, 5 - Math.floor(Math.log10(Math.abs(reference) || 1))));
  const spanDecimals = span >= 200 ? 0 : span >= 20 ? 1 : span >= 2 ? 2 : span >= 0.2 ? 3 : 4;
  const decimals = Math.max(tickDecimals, spanDecimals);
  const axisPrice = (value: number) =>
    value.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  // A 4h or 1d series labels every bar with the same clock time; show the date instead.
  const windowMs =
    candles.length > 1
      ? new Date(candles[candles.length - 1]!.ts).getTime() - new Date(candles[0]!.ts).getTime()
      : 0;
  const dateAxis = windowMs > 36 * 60 * 60 * 1000;

  const y = (price: number) => padTop + plotHeight - ((price - lo) / span) * plotHeight;
  const slot = candles.length ? plotWidth / candles.length : plotWidth;
  const x = (index: number) => slot * index + slot / 2;
  const bodyWidth = Math.max(1.4, Math.min(16, slot * 0.62));

  const last = candles.at(-1);
  const prev = candles.at(-2);
  const trendUp = last && prev ? last.close >= prev.close : true;
  const liveColor = trendUp ? UP : DOWN;

  const emaValues = React.useMemo(
    () => (showEma ? ema(candles.map((c) => c.close), 21) : []),
    [candles, showEma],
  );

  const vwapValues = React.useMemo(() => (showVwap ? vwap(candles) : []), [candles, showVwap]);
  const rsiValues = React.useMemo(
    () => (showRsi ? rsi(candles.map((c) => c.close), 14) : []),
    [candles, showRsi],
  );
  const rsiY = (value: number) => rsiTop + rsiHeight - (value / 100) * rsiHeight;
  const rsiPath = rsiValues.reduce((path, value, index) => {
    if (value === null) return path;
    const previous = index > 0 ? rsiValues[index - 1] : null;
    return `${path}${previous === null || previous === undefined ? "M" : "L"}${x(index).toFixed(2)},${rsiY(value).toFixed(2)} `;
  }, "");
  const lastRsi = [...rsiValues].reverse().find((value) => value !== null) ?? null;

  const maxVolume = Math.max(1, ...candles.map((c) => c.volume ?? 0));

  const linePath = candles
    .map((candle, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(candle.close).toFixed(2)}`)
    .join(" ");

  const handlePointer = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * width;
    const py = ((event.clientY - rect.top) / rect.height) * height;
    if (px > plotWidth) return;
    const index = Math.max(0, Math.min(candles.length - 1, Math.round((px - slot / 2) / slot)));
    const price = lo + ((padTop + plotHeight - py) / plotHeight) * span;

    if (tool !== "none" && onDraw) {
      if (tool === "hline") {
        onDraw({ id: `h-${Date.now()}`, type: "hline", price });
      } else if (!pending) {
        setPending({ index, price });
      } else {
        onDraw({
          id: `t-${Date.now()}`,
          type: "trend",
          from: { index: pending.index, price: pending.price },
          to: { index, price },
        });
        setPending(null);
      }
      return;
    }
    setHover(showCrosshair ? { index, x: px, y: py } : null);
  };

  const hovered = hover ? candles[hover.index] : null;
  const crosshairColor = hovered && hovered.close >= hovered.open ? UP : DOWN;

  return (
    <div ref={wrapRef} className={cn("relative w-full select-none", className)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={ariaLabel}
        className={cn("block touch-pan-y", tool !== "none" ? "cursor-crosshair" : "cursor-default")}
        onPointerMove={handlePointer}
        onPointerLeave={() => setHover(null)}
        onPointerDown={tool === "trend" ? handlePointer : undefined}
      >
        <defs>
          <linearGradient id="chart-area-up" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={UP} stopOpacity="0.34" />
            <stop offset="100%" stopColor={UP} stopOpacity="0" />
          </linearGradient>
          <linearGradient id="chart-area-down" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={DOWN} stopOpacity="0.34" />
            <stop offset="100%" stopColor={DOWN} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* horizontal grid + price rail */}
        {ticks(lo, hi, 5).map((price) => (
          <g key={price}>
            <line x1={0} x2={plotWidth} y1={y(price)} y2={y(price)} stroke={GRID} strokeWidth={1} />
            {/* The live chip owns this band of the rail; a label under it is unreadable. */}
            {livePrice !== null && Math.abs(y(price) - y(livePrice)) < 11 ? null : (
              <text
                /* Right-aligned inside the rail: a six-digit price would otherwise run
                   past the SVG edge and lose its last digits. */
                x={width - 6}
                textAnchor="end"
                y={y(price) + 3}
                fill={AXIS_TEXT}
                fontSize={9}
                fontFamily="var(--font-mono, monospace)"
              >
                {axisPrice(price)}
              </text>
            )}
          </g>
        ))}
        <line x1={plotWidth} x2={plotWidth} y1={padTop} y2={padTop + plotHeight} stroke={GRID} strokeWidth={1} />

        {/* volume histogram */}
        {showVolume
          ? candles.map((candle, index) => {
              const vol = candle.volume ?? 0;
              const barHeight = (vol / maxVolume) * Math.max(6, volumeHeight - 4);
              const up = candle.close >= candle.open;
              return (
                <rect
                  key={`v-${candle.ts}-${index}`}
                  x={x(index) - bodyWidth / 2}
                  y={padTop + plotHeight + (volumeHeight - barHeight)}
                  width={bodyWidth}
                  height={barHeight}
                  fill={up ? UP : DOWN}
                  opacity={0.22}
                />
              );
            })
          : null}

        {mode === "candles" ? (
          <g>
            {candles.map((candle, index) => {
              const up = candle.close >= candle.open;
              const color = up ? UP : DOWN;
              const openY = y(candle.open);
              const closeY = y(candle.close);
              const top = Math.min(openY, closeY);
              const bodyHeight = Math.max(1.2, Math.abs(closeY - openY));
              return (
                <g key={`${candle.ts}-${index}`}>
                  <line
                    x1={x(index)}
                    x2={x(index)}
                    y1={y(candle.high)}
                    y2={y(candle.low)}
                    stroke={color}
                    strokeWidth={Math.max(1, Math.min(2, bodyWidth * 0.16))}
                  />
                  <rect
                    x={x(index) - bodyWidth / 2}
                    y={top}
                    width={bodyWidth}
                    height={bodyHeight}
                    fill={color}
                    rx={bodyWidth > 5 ? 1 : 0}
                  />
                </g>
              );
            })}
          </g>
        ) : (
          <g>
            <path
              d={`${linePath} L${x(candles.length - 1).toFixed(2)},${padTop + plotHeight} L${x(0).toFixed(2)},${padTop + plotHeight} Z`}
              fill={trendUp ? "url(#chart-area-up)" : "url(#chart-area-down)"}
            />
            <path d={linePath} fill="none" stroke={liveColor} strokeWidth={2} strokeLinejoin="round" />
          </g>
        )}

        {/* EMA overlay */}
        {showEma && emaValues.length ? (
          <path
            d={emaValues
              .map((value, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(value).toFixed(2)}`)
              .join(" ")}
            fill="none"
            stroke={EMA_COLOR}
            strokeWidth={1.4}
            opacity={0.9}
          />
        ) : null}

        {/* session VWAP */}
        {showVwap && vwapValues.length ? (
          <g>
            <path
              d={vwapValues
                .map((value, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(value).toFixed(2)}`)
                .join(" ")}
              fill="none"
              stroke={VWAP_COLOR}
              strokeWidth={1.2}
              strokeDasharray="5 3"
              opacity={0.85}
            />
            <text
              x={plotWidth - 4}
              y={y(vwapValues[vwapValues.length - 1] as number) - 5}
              fill={VWAP_COLOR}
              fontSize={9}
              textAnchor="end"
              fontFamily="var(--font-mono, monospace)"
            >
              VWAP {fmtPrice(vwapValues[vwapValues.length - 1] as number)}
            </text>
          </g>
        ) : null}

        {/* saved drawings */}
        {drawings.map((drawing) =>
          drawing.type === "hline" ? (
            <g key={drawing.id}>
              <line
                x1={0}
                x2={plotWidth}
                y1={y(drawing.price)}
                y2={y(drawing.price)}
                stroke={EMA_COLOR}
                strokeWidth={1}
                strokeDasharray="6 4"
                opacity={0.75}
              />
              <text x={6} y={y(drawing.price) - 4} fill={EMA_COLOR} fontSize={9} fontFamily="var(--font-mono, monospace)">
                {fmtPrice(drawing.price)}
              </text>
            </g>
          ) : (
            <line
              key={drawing.id}
              x1={x(drawing.from.index)}
              y1={y(drawing.from.price)}
              x2={x(drawing.to.index)}
              y2={y(drawing.to.price)}
              stroke={EMA_COLOR}
              strokeWidth={1.4}
              opacity={0.85}
            />
          ),
        )}

        {pending ? <circle cx={x(pending.index)} cy={y(pending.price)} r={3} fill={EMA_COLOR} /> : null}

        {/* stop-loss and take-profit bands */}
        {stopLoss ? (
          <g>
            <line
              x1={0}
              x2={plotWidth}
              y1={y(stopLoss)}
              y2={y(stopLoss)}
              stroke={DOWN}
              strokeWidth={1}
              strokeDasharray="4 4"
              opacity={0.8}
            />
            <text x={6} y={y(stopLoss) - 4} fill={DOWN} fontSize={9} fontFamily="var(--font-mono, monospace)">
              SL {fmtPrice(stopLoss)}
            </text>
          </g>
        ) : null}
        {takeProfit ? (
          <g>
            <line
              x1={0}
              x2={plotWidth}
              y1={y(takeProfit)}
              y2={y(takeProfit)}
              stroke={UP}
              strokeWidth={1}
              strokeDasharray="4 4"
              opacity={0.8}
            />
            <text x={6} y={y(takeProfit) - 4} fill={UP} fontSize={9} fontFamily="var(--font-mono, monospace)">
              TP {fmtPrice(takeProfit)}
            </text>
          </g>
        ) : null}

        {/* contract entry */}
        {entryPrice ? (
          <g>
            <line
              x1={0}
              x2={plotWidth}
              y1={y(entryPrice)}
              y2={y(entryPrice)}
              stroke="rgb(var(--vt-text))"
              strokeWidth={1}
              strokeDasharray="2 3"
              opacity={0.7}
            />
            {/* Anchored on the left so it never collides with the live-quote chip. */}
            <rect
              x={2}
              y={y(entryPrice) - 8}
              width={54}
              height={16}
              rx={3}
              fill="rgb(var(--vt-bg-800))"
              stroke="rgba(255,255,255,0.22)"
            />
            <text
              x={29}
              y={y(entryPrice) + 3}
              fill={entryDirection === "put" || entryDirection === "sell" ? DOWN : UP}
              fontSize={9}
              textAnchor="middle"
              fontFamily="var(--font-mono, monospace)"
            >
              {(entryDirection ?? "entry").toUpperCase()}
            </text>
          </g>
        ) : null}

        {/* live quote */}
        {livePrice ? (
          <g>
            <line
              x1={0}
              x2={plotWidth}
              y1={y(livePrice)}
              y2={y(livePrice)}
              stroke={liveColor}
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.55}
            />
            <rect x={plotWidth + 1} y={y(livePrice) - 8} width={railWidth - 3} height={16} rx={3} fill={liveColor} />
            <text
              x={plotWidth + railWidth / 2}
              y={y(livePrice) + 3.5}
              fill="rgb(var(--vt-bg))"
              fontSize={9}
              fontWeight={700}
              textAnchor="middle"
              fontFamily="var(--font-mono, monospace)"
            >
              {fmtPrice(livePrice)}
            </text>
            <circle cx={x(candles.length - 1)} cy={y(livePrice)} r={2.6} fill={liveColor} />
          </g>
        ) : null}

        {/* crosshair */}
        {hover && hovered ? (
          <g pointerEvents="none">
            <line
              x1={hover.x}
              x2={hover.x}
              y1={padTop}
              y2={padTop + plotHeight}
              stroke={crosshairColor}
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.6}
            />
            <line
              x1={0}
              x2={plotWidth}
              y1={hover.y}
              y2={hover.y}
              stroke={crosshairColor}
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.6}
            />
          </g>
        ) : null}

        {/* RSI pane */}
        {showRsi && rsiHeight ? (
          <g>
            <line x1={0} x2={plotWidth} y1={rsiTop} y2={rsiTop} stroke={GRID} strokeWidth={1} />
            {[30, 70].map((level) => (
              <g key={level}>
                <line
                  x1={0}
                  x2={plotWidth}
                  y1={rsiY(level)}
                  y2={rsiY(level)}
                  stroke={GRID}
                  strokeDasharray="2 3"
                />
                <text
                  x={plotWidth + 8}
                  y={rsiY(level) + 3}
                  fill={AXIS_TEXT}
                  fontSize={9}
                  fontFamily="var(--font-mono, monospace)"
                >
                  {level}
                </text>
              </g>
            ))}
            {rsiPath ? <path d={rsiPath} fill="none" stroke={EMA_COLOR} strokeWidth={1.2} /> : null}
            <text x={6} y={rsiTop + 11} fill={AXIS_TEXT} fontSize={9} fontFamily="var(--font-mono, monospace)">
              RSI 14{lastRsi === null ? "" : ` · ${lastRsi.toFixed(1)}`}
            </text>
          </g>
        ) : null}

        {/* time axis */}
        {candles.length
          ? [0, Math.floor(candles.length / 3), Math.floor((candles.length * 2) / 3), candles.length - 1].map((index, position, all) => {
              const candle = candles[index];
              if (!candle) return null;
              const isFirst = position === 0;
              const isLast = position === all.length - 1;
              return (
                <text
                  key={`t-${index}`}
                  x={isFirst ? 2 : isLast ? plotWidth - 2 : x(index)}
                  y={height - 4}
                  fill={AXIS_TEXT}
                  fontSize={9}
                  textAnchor={isFirst ? "start" : isLast ? "end" : "middle"}
                  fontFamily="var(--font-mono, monospace)"
                >
                  {dateAxis
                    ? new Date(candle.ts).toLocaleDateString([], { day: "2-digit", month: "short" })
                    : new Date(candle.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </text>
              );
            })
          : null}
      </svg>

      {hover && hovered ? (
        <div className="pointer-events-none absolute left-2 top-2 flex gap-3 rounded-md border border-line-soft bg-obsidian-950/90 px-2 py-1 font-mono text-3xs backdrop-blur">
          {([
            ["O", hovered.open],
            ["H", hovered.high],
            ["L", hovered.low],
            ["C", hovered.close],
          ] as const).map(([label, value]) => (
            <span key={label} className="text-paper-faint">
              {label}
              <span className="ml-1" style={{ color: hovered.close >= hovered.open ? UP : DOWN }}>
                {fmtPrice(value)}
              </span>
            </span>
          ))}
        </div>
      ) : null}

      {!candles.length ? (
        <div className="absolute inset-0 grid place-items-center text-xs text-paper-faint">Waiting for price data…</div>
      ) : null}
    </div>
  );
}
