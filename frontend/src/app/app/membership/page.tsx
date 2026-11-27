"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowUpRight, Check, Clock, Info, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { usePresence } from "@/lib/presence";
import { automationSummary, capLabel, tierFor } from "@/lib/membership";
import { dateOnly, money } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { ErrorNote, Skeleton } from "@/components/ui/data";
import { SectionHeading } from "@/components/ui/panel";
import { TierBadge } from "@/components/app/tier-badge";
import { cn } from "@/lib/cn";

type Plan = {
  code: string;
  name: string;
  tagline: string;
  price_monthly: number;
  currency: string;
  features: string[];
  limits: Record<string, number | string[] | boolean | null>;
  trial_days: number;
};

const MODE_COPY: Record<string, { title: string; body: string }> = {
  none: {
    title: "No automation",
    body: "Manual orders and simulation only. Automated strategies cannot be switched on.",
  },
  session: {
    title: "Session automation",
    body: "Strategies run only while this workspace is open. Close the tab and they stop within a minute.",
  },
  background: {
    title: "Background automation",
    body: "Strategies keep running when you close the platform, within your plan's trade allowance.",
  },
};

function num(limits: Record<string, unknown>, key: string): number | null {
  const value = limits?.[key];
  return typeof value === "number" ? value : null;
}

export default function MembershipPage() {
  const { entitlements, subscription, automation: meAutomation } = useAuth();
  const { automation: live } = usePresence();
  const plans = useApi<{ plans: Plan[] }>((signal) => api("/plans", { signal }));

  const planCode = entitlements?.plan_code ?? subscription?.plan_code ?? "free";
  const tier = tierFor(planCode);
  const automation = live ?? meAutomation;
  const summary = automationSummary(tier, automation);
  const periodEnd = subscription?.current_period_end;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Membership"
        title="Your plan, and what it may automate"
        description="Every tier can trade manually and simulate. What changes is how much automation you may run, how many accounts you can connect, and whether strategies keep running after you close the platform."
      />

      <section className="tile tile-sheen tier-glow" data-tier={tier.code} aria-label="Current membership">
        <div className="grid gap-6 p-5 lg:grid-cols-[1.2fr_1fr] lg:p-6">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <TierBadge planCode={planCode} size="md" />
              <Badge tone={subscription?.status === "active" || planCode === "free" ? "gain" : "warn"}>
                {subscription?.status ?? "active"}
              </Badge>
              {subscription?.cancel_at_period_end ? <Badge tone="warn">Cancels at period end</Badge> : null}
            </div>
            <h2 className="mt-3 font-display text-2xl text-paper">
              {tier.badge} {tier.label} membership
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-paper-muted">
              {tier.promise}. {capLabel(tier, automation?.used_today)}.
            </p>

            <dl className="mt-5 grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="metric-label">Automation</dt>
                <dd className="mt-1 text-xs text-paper">{MODE_COPY[automation?.mode ?? tier.automationMode]?.title}</dd>
              </div>
              <div>
                <dt className="metric-label">Used today</dt>
                <dd className="num mt-1 text-xs text-paper">
                  {automation
                    ? `${automation.used_today}${automation.daily_cap ? ` / ${automation.daily_cap}` : ""}`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="metric-label">{subscription?.cancel_at_period_end ? "Ends" : "Renews"}</dt>
                <dd className="mt-1 text-xs text-paper">{periodEnd ? dateOnly(periodEnd) : "No renewal — Free"}</dd>
              </div>
            </dl>

            <div className="mt-5 flex flex-wrap gap-2">
              <Link
                href="/app/billing"
                className="cta-gold inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-2xs font-semibold"
              >
                {"elite vip".includes(planCode) ? "Manage subscription" : "Compare and upgrade"}
                <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
              <Link
                href="/app/accounts"
                className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3.5 py-2 text-2xs text-paper-muted transition hover:bg-obsidian-700/70 hover:text-paper"
              >
                Connected accounts
              </Link>
            </div>
          </div>

          <div
            className={cn(
              "rounded-xl border p-4",
              summary.tone === "gain"
                ? "border-gain/25 bg-gain/[0.06]"
                : summary.tone === "warn"
                  ? "border-warn/25 bg-warn/[0.06]"
                  : "border-line-soft bg-obsidian-900/60",
            )}
          >
            <p className="flex items-center gap-2 text-xs font-medium text-paper">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  summary.tone === "gain"
                    ? "animate-pulse bg-gain"
                    : summary.tone === "warn"
                      ? "bg-warn"
                      : "bg-paper-faint",
                )}
                aria-hidden
              />
              {summary.title}
            </p>
            <p className="mt-1.5 text-2xs leading-relaxed text-paper-muted">{summary.detail}</p>
            <ul className="mt-3 space-y-1.5 text-2xs text-paper-faint">
              {(automation?.blockers ?? []).slice(1).map((blocker) => (
                <li key={blocker} className="flex gap-2">
                  <Clock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                  {blocker}
                </li>
              ))}
              <li className="flex gap-2">
                <ShieldCheck className="mt-0.5 h-3 w-3 shrink-0 text-gain" aria-hidden />
                Every order still passes the independent risk engine, whatever the plan.
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section aria-label="All memberships">
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-sm font-medium text-paper">All memberships</h2>
          <p className="text-2xs text-paper-faint">Prices in USD, billed monthly. Cancel any time.</p>
        </div>

        {plans.error ? <ErrorNote message={plans.error} onRetry={plans.refetch} /> : null}
        {plans.loading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((index) => (
              <Skeleton key={index} className="h-72" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {(plans.data?.plans ?? []).map((plan) => {
              const planTier = tierFor(plan.code);
              const current = plan.code === planCode;
              const mode = MODE_COPY[String(plan.limits?.automation_mode ?? planTier.automationMode)];
              return (
                <article
                  key={plan.code}
                  className={cn(
                    "tile tile-sheen flex flex-col p-4 transition",
                    current ? "border-champagne-400/40" : "hover:border-line-strong",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <TierBadge planCode={plan.code} size="xs" />
                    {current ? (
                      <span className="text-3xs uppercase tracking-label text-champagne-600">Current</span>
                    ) : null}
                  </div>
                  <p className="mt-3 font-display text-xl text-paper">
                    {money(plan.price_monthly, plan.currency, 0)}
                    <span className="ml-1 font-sans text-2xs text-paper-faint">/ month</span>
                  </p>
                  <p className="mt-1 text-2xs leading-relaxed text-paper-faint">{plan.tagline}</p>

                  <dl className="mt-4 space-y-2 border-t border-line-soft pt-3 text-2xs">
                    <div className="flex items-start justify-between gap-2">
                      <dt className="text-paper-faint">Automation</dt>
                      <dd className="text-right text-paper-muted">{mode?.title ?? "—"}</dd>
                    </div>
                    <div className="flex items-start justify-between gap-2">
                      <dt className="text-paper-faint">Trade allowance</dt>
                      <dd className="text-right text-paper-muted">{capLabel(planTier)}</dd>
                    </div>
                    <div className="flex items-start justify-between gap-2">
                      <dt className="text-paper-faint">Accounts</dt>
                      <dd className="num text-right text-paper-muted">{num(plan.limits, "max_connections") ?? "—"}</dd>
                    </div>
                    <div className="flex items-start justify-between gap-2">
                      <dt className="text-paper-faint">Open positions</dt>
                      <dd className="num text-right text-paper-muted">
                        {num(plan.limits, "max_open_positions") ?? "—"}
                      </dd>
                    </div>
                  </dl>

                  <ul className="mt-3 flex-1 space-y-1.5 text-2xs text-paper-muted">
                    {plan.features.slice(0, 5).map((feature) => (
                      <li key={feature} className="flex gap-2">
                        <Check className="mt-0.5 h-3 w-3 shrink-0 text-gain" aria-hidden />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>

                  <Link
                    href="/app/billing"
                    className={cn(
                      "mt-4 inline-flex items-center justify-center gap-1.5 rounded-full px-3 py-2 text-2xs font-semibold transition",
                      current
                        ? "border border-line-strong text-paper-muted hover:bg-obsidian-700/70"
                        : plan.code === "pro"
                          ? "cta-gold"
                          : "border border-line-strong text-paper hover:bg-obsidian-700/70",
                    )}
                  >
                    {current ? "Manage" : `Choose ${plan.name}`}
                  </Link>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="tile p-5">
        <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
          <Info className="h-4 w-4 text-champagne-600" aria-hidden />
          What a membership never unlocks
        </h2>
        <div className="mt-3 grid gap-4 text-2xs leading-relaxed text-paper-muted md:grid-cols-3">
          <p>
            <span className="block text-paper">Real money is a separate decision.</span>
            A paid plan makes you eligible for live trading. It does not switch it on. Live execution needs explicit
            authorisation from you, a completed safety checklist, and a platform-wide enablement.
          </p>
          <p>
            <span className="block text-paper">The risk engine always runs.</span>
            Position size, exposure, daily loss, drawdown, duplicate orders and stale data are checked before any order
            leaves the platform. An AI suggestion cannot skip a check.
          </p>
          <p>
            <span className="block text-paper">Performance fees are separate.</span>
            Only Elite and VIP can be offered a performance fee agreement, and only on realised profit above a high-water mark,
            after separate consent and a legal review. It is disabled by default.
          </p>
        </div>
        <p className="mt-4 flex items-center gap-2 text-2xs text-paper-faint">
          <Sparkles className="h-3 w-3 text-gold-600" aria-hidden />
          No plan promises a return. Simulated results are not forecasts.
        </p>
      </section>
    </div>
  );
}
