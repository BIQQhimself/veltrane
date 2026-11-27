"use client";

import * as React from "react";
import Link from "next/link";
import { BadgePercent, Gift, Info, Sparkles, Users } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { tierFor } from "@/lib/membership";
import { Badge } from "@/components/ui/badge";
import { ErrorNote, Skeleton } from "@/components/ui/data";
import { SectionHeading } from "@/components/ui/panel";
import { TierBadge } from "@/components/app/tier-badge";

type Plan = { code: string; name: string; price_monthly: number; currency: string; trial_days: number };
type ReferralConfig = { enabled: boolean; url: string };
type PerformanceFee = { eligible: boolean; consent?: { granted: boolean } | null; note?: string };

/**
 * Promotions shows only what is real for this account: an unused trial, the referral programme,
 * and an Elite performance-fee agreement. There is deliberately no invented discount banner.
 */
export default function PromotionsPage() {
  const { entitlements, subscription, usage } = useAuth();
  const plans = useApi<{ plans: Plan[] }>((signal) => api("/plans", { signal }));
  const referral = useApi<ReferralConfig>((signal) => api("/referrals/config", { signal }));
  const fee = useApi<PerformanceFee>((signal) => api("/billing/performance-fee", { signal }));

  const plan = entitlements?.plan_code ?? subscription?.plan_code ?? "free";
  const tier = tierFor(plan);
  const trialPlans = (plans.data?.plans ?? []).filter((item) => item.trial_days > 0 && item.price_monthly > 0);
  const usedDemoToday = usage?.demo_executions_today ?? 0;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Promotions & rewards"
        title="Only what is actually available to you"
        description="This page lists real programmes attached to your account. If a campaign is running, it appears here with its exact terms; nothing is invented, and no discount is ever applied without a verified payment confirmation."
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <section className="tile tile-sheen flex flex-col p-5" aria-label="Free trial">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
              <Sparkles className="h-4 w-4 text-gold-300" aria-hidden />
              Trial
            </h2>
            <Badge tone={plan === "free" ? "gold" : "neutral"}>{plan === "free" ? "Available" : "In use"}</Badge>
          </div>
          {plans.loading ? (
            <Skeleton className="mt-3 h-16" />
          ) : (
            <>
              <p className="mt-3 text-2xs leading-relaxed text-paper-muted">
                {plan === "free"
                  ? `${trialPlans[0]?.trial_days ?? 7} days are available on a paid tier. The trial is granted at checkout and ends automatically — no card is charged until it expires.`
                  : "A trial has already been used on this account. Your current plan renews at its normal price."}
              </p>
              <p className="mt-2 text-3xs text-paper-faint">
                {trialPlans.length > 0
                  ? `Eligible tiers: ${trialPlans.map((item) => item.name).join(", ")}`
                  : "No tier currently offers a trial."}
              </p>
            </>
          )}
          <Link href="/app/billing" className="mt-auto pt-3 text-2xs text-champagne-300 hover:text-champagne-200">
            {plan === "free" ? "Start at checkout →" : "View billing →"}
          </Link>
        </section>

        <section className="tile tile-sheen flex flex-col p-5" aria-label="Referral rewards">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
              <Users className="h-4 w-4 text-champagne-300" aria-hidden />
              Referral programme
            </h2>
            <Badge tone={referral.data?.enabled ? "gain" : "neutral"}>
              {referral.loading ? "…" : referral.data?.enabled ? "Open" : "Not configured"}
            </Badge>
          </div>
          <p className="mt-3 text-2xs leading-relaxed text-paper-muted">
            {referral.data?.enabled
              ? "Share your Deriv link and commission is settled by Deriv under their terms. VELTRANE does not pay for self-referral and does not estimate earnings."
              : "No referral link is configured for this deployment yet."}
          </p>
          <Link href="/app/referrals" className="mt-auto pt-3 text-2xs text-champagne-300 hover:text-champagne-200">
            Open referrals →
          </Link>
        </section>

        <section className="tile tile-sheen flex flex-col p-5" aria-label="Performance fee agreement">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
              <BadgePercent className="h-4 w-4 text-gold-300" aria-hidden />
              Performance fee
            </h2>
            <TierBadge planCode={plan} size="xs" />
          </div>
          {fee.error ? (
            <p className="mt-3 text-2xs text-paper-faint">Not available on this plan.</p>
          ) : fee.loading ? (
            <Skeleton className="mt-3 h-16" />
          ) : (
            <p className="mt-3 text-2xs leading-relaxed text-paper-muted">
              {fee.data?.eligible
                ? fee.data.consent?.granted
                  ? "An agreement is on file. Fees apply only to realised profit above your high-water mark."
                  : "You are eligible. The agreement needs separate consent, applies to realised profit only, and is charged above a high-water mark after losses are recovered."
                : "Performance fees are an Elite or VIP option only, and are disabled unless a legal review has been completed."}
            </p>
          )}
          <Link href="/app/billing" className="mt-auto pt-3 text-2xs text-champagne-300 hover:text-champagne-200">
            {tier.dailyCap === null ? "Review the agreement →" : "See Elite →"}
          </Link>
        </section>
      </div>

      <section className="tile p-5" aria-label="Active campaigns">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
            <Gift className="h-4 w-4 text-gold-300" aria-hidden />
            Active campaigns
          </h2>
          <Badge tone="neutral">0 running</Badge>
        </div>
        <p className="mt-3 max-w-2xl text-2xs leading-relaxed text-paper-muted">
          No promotional campaign is running. When one is published, its terms — eligibility, dates, and what happens at
          the end — appear here before you can act on it.
        </p>
        <div className="mt-4 grid gap-3 text-2xs text-paper-faint md:grid-cols-3">
          <p className="rounded-lg border border-line-soft bg-obsidian-900/60 p-3">
            <span className="block text-paper-muted">Demo allowance</span>
            Demo executions are free and never touch real money — {usedDemoToday} used today
            {tier.dailyCap === null ? " with no VELTRANE cap." : ` of ${tier.dailyCap}.`}
          </p>
          <p className="rounded-lg border border-line-soft bg-obsidian-900/60 p-3">
            <span className="block text-paper-muted">No hidden pricing</span>
            The price shown at checkout is the price charged. No add-on fees are introduced later.
          </p>
          <p className="rounded-lg border border-line-soft bg-obsidian-900/60 p-3">
            <span className="block text-paper-muted">Refunds</span>
            Refund eligibility follows the terms you accepted. Requests go through billing, not support chat.
          </p>
        </div>
        {plans.error ? (
          <div className="mt-4">
            <ErrorNote message={plans.error} onRetry={plans.refetch} />
          </div>
        ) : null}
        <p className="mt-4 flex items-start gap-2 text-3xs text-paper-faint">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-champagne-300" aria-hidden />
          Promotions never change what the risk engine allows, and no promotion makes live trading available without the
          usual authorisation.
        </p>
      </section>
    </div>
  );
}
