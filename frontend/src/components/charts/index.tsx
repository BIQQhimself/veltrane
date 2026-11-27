"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

// Strokes read the runtime palette so an administrator's colours reach every chart.
const TONES = {
  gold: { stroke: "rgb(var(--vt-accent-400))", fill: "rgb(var(--vt-accent-400))", opacity: 0.16 },
  gain: { stroke: "rgb(var(--vt-gain))", fill: "rgb(var(--vt-gain))", opacity: 0.16 },
  loss: { stroke: "rgb(var(--vt-loss))", fill: "rgb(var(--vt-loss))", opacity: 0.16 },
  info: { stroke: "rgb(var(--vt-chart-line-500))", fill: "rgb(var(--vt-chart-line-500))", opacity: 0.16 },
  platinum: { stroke: "rgb(var(--vt-text-muted))", fill: "rgb(var(--vt-text-muted))", opacity: 0.1 },
} as const;

export type ChartTone = keyof typeof TONES;

function buildPath(values: number[], width: number, height: number, padding = 2) {
  if (values.length < 2) return { line: "", area: "" };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = (width - padding * 2) / (values.length - 1);
  const points = values.map((value, index) => {
    const x = padding + index * stepX;
    const y = padding + (1 - (value - min) / span) * (height - padding * 2);
    return [x, y] as const;
  });
  const line = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `${line} L${points[points.length - 1]![0].toFixed(2)},${height - padding} L${points[0]![0].toFixed(2)},${height - padding} Z`;
  return { line, area };
}

export function AreaChart({
  values,
  height = 180,
  tone = "gold",
  className,
  labels,
  showBaseline = true,
  ariaLabel,
  formatValue,
}: {
  values: number[];
  height?: number;
  tone?: ChartTone;
  className?: string;
  labels?: string[];
  showBaseline?: boolean;
  ariaLabel?: string;
  formatValue?: (value: number) => string;
}) {
  const width = 640;
  const id = React.useId().replace(/[:]/g, "");
  const colors = TONES[tone];
  const { line, area } = buildPath(values, width, height, 6);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;

  return (
    <figure className={cn("w-full", className)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={ariaLabel ?? "Time series chart"}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={`grad-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colors.fill} stopOpacity={colors.opacity} />
            <stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </linearGradient>
        </defs>
        {showBaseline
          ? [0.25, 0.5, 0.75].map((ratio) => (
              <line
                key={ratio}
                x1={0}
                x2={width}
                y1={height * ratio}
                y2={height * ratio}
                stroke="rgba(255,255,255,0.045)"
                strokeDasharray="3 5"
              />
            ))
          : null}
        {area ? <path d={area} fill={`url(#grad-${id})`} /> : null}
        {line ? (
          <path d={line} fill="none" stroke={colors.stroke} strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
        ) : null}
      </svg>
      <figcaption className="mt-2 flex items-center justify-between text-2xs text-paper-faint">
        <span className="num">
          {formatValue
            ? `${formatValue(min)} – ${formatValue(max)}`
            : `${min.toLocaleString(undefined, { maximumFractionDigits: 2 })} – ${max.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
        </span>
        {labels && labels.length > 1 ? (
          <span>
            {labels[0]} → {labels[labels.length - 1]}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}

export function Sparkline({
  values,
  tone = "gold",
  width = 96,
  height = 28,
  className,
}: {
  values: number[];
  tone?: ChartTone;
  width?: number;
  height?: number;
  className?: string;
}) {
  const { line } = buildPath(values, width, height, 1.5);
  if (!line) return <div className={cn("h-7 w-24", className)} aria-hidden />;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} className={className} aria-hidden>
      <path d={line} fill="none" stroke={TONES[tone].stroke} strokeWidth={1.5} strokeLinecap="round" />
    </svg>
  );
}

export function Donut({
  segments,
  size = 168,
  thickness = 14,
  centerLabel,
  centerValue,
}: {
  segments: Array<{ label: string; value: number; color: string }>;
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string;
}) {
  const total = segments.reduce((sum, segment) => sum + Math.max(0, segment.value), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#141a23" strokeWidth={thickness} />
        {total > 0 &&
          segments.map((segment) => {
            const fraction = Math.max(0, segment.value) / total;
            const dash = fraction * circumference;
            const circle = (
              <circle
                key={segment.label}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={segment.color}
                strokeWidth={thickness}
                strokeDasharray={`${dash} ${circumference - dash}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
              />
            );
            offset += dash;
            return circle;
          })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {centerValue ? <span className="num text-lg font-medium text-paper">{centerValue}</span> : null}
        {centerLabel ? <span className="label mt-1">{centerLabel}</span> : null}
      </div>
    </div>
  );
}

export function BarList({ items, tone = "gold" }: { items: Array<{ label: string; value: number }>; tone?: ChartTone }) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.label}>
          <div className="mb-1 flex items-baseline justify-between text-xs">
            <span className="text-paper-muted">{item.label}</span>
            <span className="num text-paper">{item.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
            <div
              className="h-full rounded-full"
              style={{ width: `${(item.value / max) * 100}%`, backgroundColor: TONES[tone].stroke }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
