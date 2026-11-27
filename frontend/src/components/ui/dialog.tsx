"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Desktop: a centred card. Mobile: a sheet that rises from the bottom edge, which is the
 * pattern every touch-first trading app uses — the thumb reaches it and the page behind stays
 * visible. Same component, two presentations.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-start sm:overflow-y-auto sm:p-6 lg:p-10"
      role="presentation"
    >
      <div className="fixed inset-0 bg-ink-950/80 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative z-10 flex max-h-[90vh] w-full animate-fade-up flex-col border border-line-strong bg-ink-850 shadow-lift",
          "rounded-t-3xl sm:my-6 sm:max-h-none sm:rounded-card",
          wide ? "sm:max-w-3xl" : "sm:max-w-lg",
        )}
      >
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-line-strong sm:hidden" aria-hidden />
        <div className="flex items-start justify-between gap-4 px-5 pb-4 pt-4 sm:border-b sm:border-line-soft">
          <div className="min-w-0">
            <h2 className="text-[15px] font-medium text-paper">{title}</h2>
            {description ? <p className="mt-1 text-xs leading-relaxed text-paper-faint">{description}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="-mr-1 rounded-full p-1.5 text-paper-faint transition hover:bg-obsidian-700/80 hover:text-paper"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5 sm:py-4">{children}</div>
        {footer ? (
          <div className="flex justify-end gap-2 border-t border-line-soft px-5 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))]">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: Array<{ id: string; label: string; count?: number }>;
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("no-scrollbar flex gap-1 overflow-x-auto border-b border-line-soft", className)} role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "relative whitespace-nowrap px-3 py-3 text-[13px] font-medium transition-colors",
            active === tab.id ? "text-paper" : "text-paper-faint hover:text-paper-muted",
          )}
        >
          {tab.label}
          {typeof tab.count === "number" ? (
            <span className="ml-1.5 rounded-full bg-obsidian-700/80 px-1.5 py-0.5 text-2xs text-paper-muted">{tab.count}</span>
          ) : null}
          {active === tab.id ? (
            <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-champagne-400" />
          ) : null}
        </button>
      ))}
    </div>
  );
}
