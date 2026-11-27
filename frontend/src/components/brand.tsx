"use client";

import * as React from "react";
import { cn } from "@/lib/cn";
import { useTheme } from "@/components/app/theme-provider";

/**
 * VELTRANE mark — "The Meridian".
 *
 * A hexagonal aperture cut by two counter-tapered chevrons that read as a V and as
 * an order-book spread. The emerald node marks the settlement point. Drawn as
 * geometry rather than a font glyph so it stays crisp from 16px to billboard size.
 */
export function BrandMark({ className, glow = false }: { className?: string; glow?: boolean }) {
  const id = React.useId().replace(/[:]/g, "");
  return (
    <svg viewBox="0 0 40 40" className={cn("h-8 w-8", className)} role="img" aria-label="Brand mark">
      <defs>
        <linearGradient id={`vlt-a-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="rgb(var(--vt-primary-300))" />
          <stop offset="55%" stopColor="rgb(var(--vt-primary-500))" />
          <stop offset="100%" stopColor="rgb(var(--vt-gain))" />
        </linearGradient>
        <linearGradient id={`vlt-b-${id}`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="rgb(var(--vt-primary-500))" stopOpacity="0.15" />
          <stop offset="100%" stopColor="rgb(var(--vt-gain))" stopOpacity="0.55" />
        </linearGradient>
        <radialGradient id={`vlt-c-${id}`} cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor="rgb(var(--vt-gain))" stopOpacity="0.55" />
          <stop offset="100%" stopColor="rgb(var(--vt-gain))" stopOpacity="0" />
        </radialGradient>
      </defs>

      {glow ? <circle cx="20" cy="20" r="19" fill={`url(#vlt-c-${id})`} /> : null}

      <path
        d="M20 2.6 34.9 11.3v17.4L20 37.4 5.1 28.7V11.3Z"
        fill="none"
        stroke={`url(#vlt-a-${id})`}
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M20 7.1 30.9 13.4v13.2L20 32.9 9.1 26.6V13.4Z" fill={`url(#vlt-b-${id})`} opacity="0.35" />

      {/* Counter-tapered chevrons: the V, and the bid/ask spread. */}
      <path d="M12.2 12.6h4.6L20 25.4l3.2-12.8h4.6L20 31.2Z" fill={`url(#vlt-a-${id})`} />
      <path d="M17.6 12.6h4.8L20 20.4Z" fill="rgb(var(--vt-bg))" opacity="0.72" />

      <circle cx="20" cy="31.4" r="1.7" fill="rgb(var(--vt-gain))" />
      <circle cx="20" cy="31.4" r="3.6" fill="none" stroke="rgb(var(--vt-gain))" strokeOpacity="0.35" strokeWidth="0.9" />
    </svg>
  );
}

export function Wordmark({
  className,
  compact,
  glow,
}: {
  className?: string;
  compact?: boolean;
  glow?: boolean;
}) {
  const { theme } = useTheme();
  const name = theme.branding.product_name || "VELTRANE";
  const mark = theme.branding.logo_mark || "V";
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BrandMark className={compact ? "h-7 w-7" : "h-8 w-8"} glow={glow} />
      <span className="flex flex-col leading-none">
        <span className="font-display text-[15px] font-semibold uppercase tracking-wordmark text-paper">
          {compact ? mark : name}
        </span>
        {compact ? null : (
          <span className="mt-1 text-3xs uppercase tracking-[0.2em] text-paper-faint">Trading intelligence</span>
        )}
      </span>
    </span>
  );
}

export function Monogram({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line-strong bg-obsidian-800",
        className,
      )}
      aria-hidden
    >
      <BrandMark className="h-5 w-5" />
    </span>
  );
}
