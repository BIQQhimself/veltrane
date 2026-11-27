import * as React from "react";
import { cn } from "@/lib/cn";

export function Table({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("w-full overflow-x-auto", className)}>
      {/* No forced min-width: tables live in half-width panels too, where a 640px
          floor clipped the rightmost column instead of fitting the panel. */}
      <table className="w-full min-w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return <thead className="border-b border-line-soft">{children}</thead>;
}

export function TH({
  children,
  align = "left",
  className,
}: {
  children?: React.ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "whitespace-nowrap px-3 py-2.5 text-2xs font-medium uppercase tracking-label text-paper-faint sm:px-4",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-line-soft/70">{children}</tbody>;
}

export function TR({
  children,
  onClick,
  className,
  selected,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
  selected?: boolean;
}) {
  const interactive = Boolean(onClick);
  return (
    <tr
      onClick={onClick}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={cn(
        "transition-colors duration-150",
        interactive && "cursor-pointer hover:bg-obsidian-700/55 focus:bg-obsidian-700/70 focus:outline-none",
        selected && "bg-obsidian-700/70",
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function TD({
  children,
  align = "left",
  className,
  mono,
}: {
  children?: React.ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  mono?: boolean;
}) {
  return (
    <td
      className={cn(
        "whitespace-nowrap px-3 py-3.5 text-[13px] text-paper-muted sm:px-4",
        align === "right" && "text-right",
        align === "center" && "text-center",
        mono && "num text-paper",
        className,
      )}
    >
      {children}
    </td>
  );
}
