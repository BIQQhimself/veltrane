import * as React from "react";
import { cn } from "@/lib/cn";

type Tone = "neutral" | "gain" | "loss" | "warn" | "info" | "gold" | "outline";

const tones: Record<Tone, string> = {
  neutral: "border-line-strong/70 bg-obsidian-700/60 text-paper-muted",
  gain: "border-gain/25 bg-gain/10 text-gain",
  loss: "border-loss/25 bg-loss/10 text-loss",
  warn: "border-warn/25 bg-warn/10 text-warn",
  info: "border-info/25 bg-info/10 text-info",
  gold: "border-champagne-600/35 bg-champagne-500/10 text-champagne-600",
  outline: "border-line-strong bg-transparent text-paper-muted",
};

export function Badge({
  tone = "neutral",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-2xs font-medium uppercase tracking-label",
        tones[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

const statusTones: Record<string, Tone> = {
  active: "gain",
  approved: "gain",
  filled: "gain",
  running: "gain",
  ok: "gain",
  connected: "gain",
  authorized: "gain",
  live: "gain",
  rejected: "loss",
  failed: "loss",
  error: "loss",
  revoked: "loss",
  canceled: "neutral",
  cancelled: "neutral",
  closed: "neutral",
  draft: "neutral",
  pending: "warn",
  past_due: "warn",
  paused: "warn",
  simulated: "info",
  paper: "info",
  demo: "info",
  read_only: "neutral",
};

export function StatusBadge({ status, className }: { status?: string | null; className?: string }) {
  if (!status) return <Badge tone="neutral" className={className}>unknown</Badge>;
  const tone = statusTones[status.toLowerCase()] ?? "neutral";
  return (
    <Badge tone={tone} className={className}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

export function DemoBadge({ className }: { className?: string }) {
  return (
    <Badge tone="info" className={className} title="Simulated — no real money is involved">
      Simulated
    </Badge>
  );
}
