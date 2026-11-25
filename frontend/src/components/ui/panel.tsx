import * as React from "react";
import { cn } from "@/lib/cn";

export function Panel({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("panel", className)} {...props}>
      {children}
    </div>
  );
}

type PanelHeaderProps = React.HTMLAttributes<HTMLDivElement> & {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
};

export function PanelHeader({ title, subtitle, action, className, ...props }: PanelHeaderProps) {
  return (
    <div className={cn("panel-header", className)} {...props}>
      <div className="min-w-0">
        <h2 className="truncate text-sm font-medium text-paper">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-paper-faint">{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function PanelBody({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("panel-body", className)} {...props}>
      {children}
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div>
        {eyebrow ? <p className="label mb-2">{eyebrow}</p> : null}
        <h1 className="text-2xl font-medium tracking-tight text-paper md:text-[28px]">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-sm leading-relaxed text-paper-muted">{description}</p> : null}
      </div>
      {action ? <div className="flex items-center gap-2">{action}</div> : null}
    </div>
  );
}
