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
        <h2 className="truncate text-[15px] font-medium text-paper">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs leading-relaxed text-paper-faint">{subtitle}</p> : null}
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

/**
 * The one page header every screen uses. A small eyebrow, a title that does not compete with
 * the data, one line of context, and the actions on the right.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  action,
  badge,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="label mb-2">{eyebrow}</p> : null}
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-[22px] font-medium leading-tight tracking-tight text-paper sm:text-[26px]">{title}</h1>
          {badge}
        </div>
        {description ? (
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-muted">{description}</p>
        ) : null}
      </div>
      {action ? <div className="flex flex-wrap items-center gap-2">{action}</div> : null}
    </div>
  );
}

/** Backwards-compatible alias: older screens already render <SectionHeading>. */
export function SectionHeading(props: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return <PageHeader {...props} />;
}
