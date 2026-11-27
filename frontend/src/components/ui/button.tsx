import * as React from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success" | "quiet";
type Size = "xs" | "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary:
    "bg-gradient-to-b from-champagne-300 to-champagne-500 text-on-accent shadow-[0_12px_28px_-16px_rgba(203,182,145,0.85)] hover:from-champagne-200 hover:to-champagne-400 active:from-champagne-400 active:to-champagne-600",
  secondary:
    "border border-line-strong bg-obsidian-700/50 text-paper hover:border-line-strong hover:bg-obsidian-700/80",
  ghost: "text-paper-muted hover:bg-obsidian-700/70 hover:text-paper",
  quiet: "bg-obsidian-700/80 text-paper hover:bg-obsidian-600/80",
  danger: "border border-loss/35 bg-loss/10 text-loss hover:border-loss/60 hover:bg-loss/15",
  success: "border border-gain/35 bg-gain/10 text-gain hover:border-gain/60 hover:bg-gain/15",
};

const sizes: Record<Size, string> = {
  xs: "h-7 px-2.5 text-2xs",
  sm: "h-9 px-3.5 text-xs",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-sm",
};

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", loading = false, fullWidth, disabled, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center gap-2 rounded-control font-medium tracking-wide",
        "transition duration-150 ease-smooth active:translate-y-px",
        "disabled:pointer-events-none disabled:opacity-45",
        variants[variant],
        sizes[size],
        fullWidth && "w-full",
        className,
      )}
      {...props}
    >
      {loading && (
        <span
          aria-hidden
          className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
});
