"use client";

import * as React from "react";
import Link from "next/link";
import { Activity, ArrowRight, Clock, Radio, ShieldAlert, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { usePresence } from "@/lib/presence";
import { automationSummary, tierFor } from "@/lib/membership";
import { cn } from "@/lib/cn";

/**
 * One line that answers "is anything trading right now, and what would stop it".
 * Every value comes from the server snapshot, so it cannot drift from what the runner enforces.
 */
export function AutomationStrip() {
  const { entitlements, subscription } = useAuth();
  const { automation } = usePresence();
  const plan = entitlements?.plan_code ?? subscription?.plan_code ?? "free";
  const tier = tierFor(plan);

  if (!automation) {
    return (
      <div className="tile flex flex-wrap items-center gap-3 p-3 text-2xs text-paper-faint" aria-busy>
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-paper-faint" aria-hidden />
        Reading automation state…
      </div>
    );
  }

  const summary = automationSummary(tier, automation);
  const live = automation.allowed;
  const remaining = automation.remaining_today;

  return (
    <div className="tile tile-sheen flex flex-wrap items-center gap-x-5 gap-y-2 p-3">
      <div className="flex min-w-0 items-center gap-2.5">
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            live ? "bg-gain/12 text-gain" : "bg-warn/12 text-warn",
          )}
          aria-hidden
        >
          {automation.mode === "none" ? <ShieldAlert className="h-4 w-4" /> : <Activity className="h-4 w-4" />}
        </span>
        <div className="min-w-0">
          <p className="truncate text-xs text-paper">{summary.title}</p>
          <p className="truncate text-3xs text-paper-faint">
            {automation.label && automation.label !== summary.title ? automation.label : summary.detail}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1.5 text-2xs text-paper-muted">
        <Radio
          className={cn("h-3.5 w-3.5", automation.session_online ? "text-gain" : "text-paper-faint")}
          aria-hidden
        />
        {automation.mode === "background"
          ? "Background — no session needed"
          : automation.session_online
            ? "Session live"
            : "Session offline"}
      </div>

      <div className="flex items-center gap-1.5 text-2xs text-paper-muted">
        <Clock className="h-3.5 w-3.5 text-paper-faint" aria-hidden />
        <span className="num">{automation.used_today}</span>
        <span className="text-paper-faint">
          {automation.daily_cap === null ? "automated entries today · no cap" : `of ${automation.daily_cap} today`}
        </span>
      </div>

      {remaining !== null ? (
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-3xs",
            remaining > 0 ? "border-line-soft text-paper-muted" : "border-warn/30 bg-warn/10 text-warn",
          )}
        >
          {remaining > 0 ? `${remaining} left` : "allowance used"}
        </span>
      ) : null}

      <div className="ml-auto flex items-center gap-3">
        <span className="hidden items-center gap-1.5 text-3xs text-paper-faint sm:flex">
          <ShieldCheck className="h-3 w-3 text-gain/70" aria-hidden />
          Risk engine enforced
        </span>
        <Link href="/app/membership" className="inline-flex items-center gap-1 text-2xs text-champagne-300 hover:text-champagne-200">
          {automation.mode === "none" ? "Unlock automation" : "Plan details"}
          <ArrowRight className="h-3 w-3" aria-hidden />
        </Link>
      </div>

      {!live && automation.blockers.length > 0 ? (
        <p className="w-full border-t border-line-soft pt-2 text-3xs text-warn">{automation.blockers[0]}</p>
      ) : null}
    </div>
  );
}
