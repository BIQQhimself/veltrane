import * as React from "react";
import { cn } from "@/lib/cn";

export function Stat({
  label,
  value,
  delta,
  hint,
  tone = "neutral",
  className,
  children,
}: {
  label: string;
  value: React.ReactNode;
  delta?: React.ReactNode;
  hint?: string;
  tone?: "neutral" | "gain" | "loss";
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn("panel p-5", className)}>
      <p className="label">{label}</p>
      <p
        className={cn(
          "num mt-3 text-[26px] font-medium leading-none tracking-tight",
          tone === "gain" && "text-gain",
          tone === "loss" && "text-loss",
          tone === "neutral" && "text-paper",
        )}
      >
        {value}
      </p>
      <div className="mt-2 flex items-center gap-2 text-xs text-paper-faint">
        {delta ? <span>{delta}</span> : null}
        {hint ? <span>{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

export function KeyValue({ items }: { items: Array<{ label: string; value: React.ReactNode; mono?: boolean }> }) {
  return (
    <dl className="divide-y divide-line-soft/70">
      {items.map((item) => (
        <div key={item.label} className="flex items-baseline justify-between gap-6 py-2.5">
          <dt className="text-xs text-paper-faint">{item.label}</dt>
          <dd className={cn("text-right text-sm text-paper", item.mono && "num")}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      {icon ? <div className="text-paper-faint/70">{icon}</div> : null}
      <p className="text-sm font-medium text-paper">{title}</p>
      {description ? <p className="max-w-sm text-xs leading-relaxed text-paper-faint">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-md", className)} />;
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-loss/30 bg-loss/5 px-4 py-3">
      <p className="text-xs text-loss">{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="text-xs text-paper underline decoration-line-strong underline-offset-4">
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function Progress({ value, max = 100, tone = "gold" }: { value: number; max?: number; tone?: "gold" | "gain" | "loss" | "info" }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const fill =
    tone === "gain" ? "bg-gain" : tone === "loss" ? "bg-loss" : tone === "info" ? "bg-info" : "bg-champagne-500";
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={cn("h-full rounded-full transition-all duration-500", fill)} style={{ width: `${pct}%` }} />
    </div>
  );
}
