"use client";

import { cn } from "@/lib/cn";
import { capLabel, TIERS, tierFor, type Tier } from "@/lib/membership";

const ringTone: Record<Tier["accent"], string> = {
  neutral: "border-line-strong bg-obsidian-750 text-paper-muted",
  info: "border-champagne-400/40 bg-champagne-500/12 text-champagne-600",
  gold: "border-gold-400/45 bg-gold-500/12 text-gold-600",
};

/** The tier chip. The emoji is decorative; the label and `aria-label` carry the meaning. */
export function TierBadge({
  planCode,
  size = "sm",
  showLabel = true,
  className,
}: {
  planCode?: string | null;
  size?: "xs" | "sm" | "md";
  showLabel?: boolean;
  className?: string;
}) {
  const tier = tierFor(planCode);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium uppercase tracking-label",
        ringTone[tier.accent],
        size === "xs" && "px-1.5 py-0.5 text-3xs",
        size === "sm" && "px-2 py-0.5 text-2xs",
        size === "md" && "px-2.5 py-1 text-2xs",
        className,
      )}
      title={`${tier.label} membership — ${capLabel(tier)}`}
      aria-label={`${tier.label} membership`}
    >
      <span aria-hidden className={cn(size === "md" ? "text-[13px]" : "text-[11px]")}>
        {tier.badge}
      </span>
      {showLabel ? <span>{tier.label}</span> : null}
    </span>
  );
}

/** Round avatar: initials over the trader's colour, framed by a ring that encodes the tier. */
export function IdentityAvatar({
  name,
  color,
  planCode,
  size = 36,
  showBadge = true,
  className,
}: {
  name: string;
  color?: string;
  planCode?: string | null;
  size?: number;
  showBadge?: boolean;
  className?: string;
}) {
  const tier = tierFor(planCode);
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <span className={cn("relative inline-flex shrink-0", className)} style={{ width: size, height: size }}>
      <span className="identity-ring flex h-full w-full" data-tier={tier.code}>
        <span
          className="flex h-full w-full items-center justify-center rounded-full font-medium text-on-accent"
          style={{
            background: `linear-gradient(150deg, ${color ?? "#C8A96A"}, ${color ?? "#C8A96A"}cc)`,
            fontSize: Math.max(10, Math.round(size * 0.34)),
          }}
          aria-hidden
        >
          {letters || "V"}
        </span>
      </span>
      {showBadge ? (
        <span
          className="absolute -bottom-1 -right-1 flex items-center justify-center rounded-full border border-obsidian-950 bg-obsidian-800 text-[9px] leading-none"
          style={{ width: Math.round(size * 0.42), height: Math.round(size * 0.42) }}
          aria-hidden
        >
          {tier.badge}
        </span>
      ) : null}
    </span>
  );
}

export function TierName({ planCode }: { planCode?: string | null }) {
  const tier = tierFor(planCode);
  return (
    <span className="text-2xs text-paper-faint">
      {tier.badge} {tier.label}
    </span>
  );
}

export { TIERS };
