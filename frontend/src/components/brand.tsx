import { cn } from "@/lib/cn";

export function Wordmark({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-baseline gap-2", className)}>
      <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0 self-center" aria-hidden>
        <defs>
          <linearGradient id="vmark" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#e7d3a6" />
            <stop offset="100%" stopColor="#a8894f" />
          </linearGradient>
        </defs>
        <path d="M3 5h3.6L12 18.2 17.4 5H21L12 23 3 5Z" fill="url(#vmark)" opacity="0.92" />
        <path d="M9.2 5h5.6L12 12.4 9.2 5Z" fill="#05070d" opacity="0.55" />
      </svg>
      <span className="text-[15px] font-medium uppercase tracking-[0.34em] text-paper">
        {compact ? "V" : "VELTRANE"}
      </span>
    </span>
  );
}

export function Monogram({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-lg border border-champagne-600/40 bg-champagne-500/10 text-xs font-medium text-champagne-300",
        className,
      )}
      aria-hidden
    >
      V
    </div>
  );
}
