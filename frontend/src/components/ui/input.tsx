import * as React from "react";
import { cn } from "@/lib/cn";

const base =
  "w-full rounded-control border border-line-strong bg-obsidian-900/80 px-3.5 text-sm text-paper placeholder:text-paper-faint/70 " +
  "transition duration-150 ease-smooth hover:border-line-strong " +
  "focus:border-champagne-500/70 focus:outline-none focus:ring-2 focus:ring-champagne-500/15 focus-visible:outline-none disabled:opacity-50";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(base, "h-11", className)} {...props} />;
  },
);

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...props }, ref) {
    return (
      <select ref={ref} className={cn(base, "h-11 appearance-none pr-8", className)} {...props}>
        {children}
      </select>
    );
  },
);

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(base, "min-h-24 py-2.5", className)} {...props} />;
  },
);

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-paper-muted">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-loss" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-paper-faint">{hint}</p>
      ) : null}
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div>
        <p className="text-sm text-paper">{label}</p>
        {description ? <p className="mt-0.5 text-xs text-paper-faint">{description}</p> : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition-colors duration-200",
          checked ? "border-champagne-500/60 bg-champagne-500/80" : "border-line-strong bg-obsidian-700",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4.5 w-4.5 rounded-full transition-all duration-200",
            checked ? "left-[22px] bg-ink-950" : "left-0.5 bg-paper-faint",
          )}
          style={{ height: 18, width: 18 }}
        />
      </button>
    </div>
  );
}
