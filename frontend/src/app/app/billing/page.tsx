"use client";

import * as React from "react";
import { CheckCircle2, Info } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, money, titleCase } from "@/lib/format";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, KeyValue, Skeleton } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";

type Plan = {
  code: string;
  name: string;
  tagline: string;
  price_monthly: number;
  currency: string;
  features: string[];
  limits: Record<string, number | null>;
  trial_days: number;
};

type SubscriptionResponse = {
  subscription: {
    plan_code: string;
    status: string;
    current_period_start: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    canceled_at: string | null;
    pending_plan_code: string | null;
  } | null;
  effective_plan_code: string;
  entitlements: { features: Record<string, boolean>; limits: Record<string, number | null> };
};

type Invoice = {
  id: string;
  number: string;
  total: number;
  currency: string;
  status: string;
  period_start: string | null;
  period_end: string | null;
  paid_at: string | null;
};

type Checkout = { mode?: string; checkout_token?: string; checkout_url?: string; provider?: string };

type PerformanceFee = {
  eligible: boolean;
  consent?: { granted: boolean; version?: string; granted_at?: string } | null;
  high_water_mark?: number | null;
  records?: Array<{ id: string; period_start: string; period_end: string; realized_pnl: number; fee_amount: number; status: string }>;
  terms?: { rate_pct?: number; hurdle_pct?: number; basis?: string } | null;
  note?: string;
};

const LIMIT_LABELS: Array<[string, string]> = [
  ["max_connections", "Connected accounts"],
  ["max_open_positions", "Simultaneous positions"],
  ["max_daily_demo_executions", "Demo executions / day"],
  ["max_backtests_per_day", "Backtests / day"],
];

export default function BillingPage() {
  const toast = useToast();
  const { refresh } = useAuth();
  const plans = useApi<{ plans: Plan[] }>((signal) => api("/plans", { signal }));
  const subscription = useApi<SubscriptionResponse>((signal) => api("/billing/subscription", { signal }));
  const invoices = useApi<{ invoices: Invoice[] }>((signal) => api("/billing/invoices", { signal }));
  const fee = useApi<PerformanceFee>((signal) => api("/billing/performance-fee", { signal }));

  const [selected, setSelected] = React.useState<Plan | null>(null);
  const [checkout, setCheckout] = React.useState<Checkout | null>(null);
  const [busy, setBusy] = React.useState(false);

  const current = subscription.data?.effective_plan_code ?? "free";
  const sub = subscription.data?.subscription;
  const feeEligible = fee.data?.eligible;

  async function startCheckout(plan: Plan) {
    setBusy(true);
    try {
      const result = await api<Checkout>("/billing/checkout", { method: "POST", body: { plan_code: plan.code } });
      if (result.checkout_url) {
        window.location.href = result.checkout_url;
        return;
      }
      setCheckout(result);
      setSelected(plan);
    } catch (error) {
      toast.error("Checkout could not start", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function completeMock() {
    if (!checkout?.checkout_token) return;
    setBusy(true);
    try {
      await api("/billing/mock/complete", { method: "POST", body: { checkout_token: checkout.checkout_token } });
      toast.success("Simulated payment confirmed", "Entitlements were applied by the verified webhook path.");
      setSelected(null);
      setCheckout(null);
      subscription.refetch();
      invoices.refetch();
      await refresh();
    } catch (error) {
      toast.error("Payment completion failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function changePlan(plan: Plan) {
    setBusy(true);
    try {
      await api("/billing/change-plan", { method: "POST", body: { plan_code: plan.code } });
      toast.success("Plan updated", `You are now on ${plan.name}.`);
      subscription.refetch();
      await refresh();
    } catch (error) {
      toast.error("Plan change failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function cancel(immediate: boolean) {
    setBusy(true);
    try {
      await api("/billing/cancel", { method: "POST", body: { immediate } });
      toast.info(immediate ? "Subscription cancelled" : "Cancellation scheduled", immediate ? "Access to paid features ended." : "Access continues until the period ends.");
      subscription.refetch();
      await refresh();
    } catch (error) {
      toast.error("Cancellation failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Subscription"
        title="Billing & plan"
        description="Capability unlocks, not hidden metering. Plan changes take effect through the billing provider; the frontend never decides entitlement."
        action={<Badge tone="gold">{titleCase(current)}</Badge>}
      />

      {subscription.error ? <ErrorNote message={subscription.error} onRetry={subscription.refetch} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <Panel>
          <PanelHeader title="Current subscription" />
          <PanelBody className="space-y-3">
            {subscription.loading ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <>
                <KeyValue
                  items={[
                    { label: "Plan", value: titleCase(current) },
                    { label: "Status", value: <StatusBadge status={sub?.status ?? "active"} /> },
                    { label: "Renews", value: sub?.plan_code === "free" ? "Not applicable" : dateTime(sub?.current_period_end ?? null) },
                    { label: "Cancels at period end", value: sub?.cancel_at_period_end ? "Yes" : "No" },
                    { label: "Pending plan", value: sub?.pending_plan_code ? titleCase(sub.pending_plan_code) : "None" },
                  ]}
                />
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <Button variant="secondary" size="sm" onClick={() => cancel(false)} disabled={busy || current === "free"}>
                    Cancel at period end
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => cancel(true)} disabled={busy || current === "free"}>
                    Cancel immediately
                  </Button>
                </div>
              </>
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Entitlements" subtitle="Resolved server-side on every request" />
          <PanelBody>
            {subscription.loading ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <>
                <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                  {LIMIT_LABELS.map(([key, label]) => (
                    <div key={key} className="flex items-center justify-between border-b border-line-soft/60 py-1.5 text-xs">
                      <span className="text-paper-faint">{label}</span>
                      <span className="num text-paper">
                        {subscription.data?.entitlements.limits[key] ?? "—"}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {Object.entries(subscription.data?.entitlements.features ?? {})
                    .filter(([, enabled]) => enabled)
                    .map(([feature]) => (
                      <Badge key={feature} tone="outline">
                        {feature.replace(/_/g, " ")}
                      </Badge>
                    ))}
                </div>
              </>
            )}
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Plans" subtitle="Prices set by the operator" />
        <PanelBody>
          {plans.loading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {(plans.data?.plans ?? []).map((plan) => {
                const isCurrent = plan.code === current;
                return (
                  <div
                    key={plan.code}
                    className={`flex flex-col rounded-xl border p-4 ${
                      isCurrent ? "border-champagne-600/50 bg-champagne-500/[0.05]" : "border-line-soft"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-paper">{plan.name}</p>
                      {isCurrent ? <Badge tone="gold">current</Badge> : null}
                    </div>
                    <p className="num mt-3 text-2xl text-paper">
                      {money(plan.price_monthly, plan.currency, 0)}
                      <span className="text-2xs text-paper-faint"> /mo</span>
                    </p>
                    <p className="mt-1 text-2xs text-paper-faint">{plan.tagline}</p>
                    <ul className="mt-3 flex-1 space-y-1.5">
                      {(plan.features ?? []).slice(0, 5).map((feature) => (
                        <li key={feature} className="flex items-start gap-1.5 text-2xs text-paper-muted">
                          <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-champagne-500/70" aria-hidden />
                          {feature}
                        </li>
                      ))}
                    </ul>
                    {plan.code === "free" ? (
                      <p className="mt-3 text-center text-2xs text-paper-faint">Included with every account</p>
                    ) : isCurrent ? (
                      <p className="mt-3 text-center text-2xs text-paper-faint">Your current plan</p>
                    ) : (
                      <Button
                        size="sm"
                        variant="secondary"
                        className="mt-3"
                        disabled={busy}
                        onClick={() => (current === "free" ? startCheckout(plan) : changePlan(plan))}
                      >
                        {current === "free" ? "Subscribe" : "Switch"}
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <p className="mt-4 flex items-start gap-2 text-2xs leading-relaxed text-paper-faint">
            <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            A paid plan never enables live trading by itself. Live execution also needs explicit authorisation, a
            verified connection and an open platform gate.
          </p>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Invoices" subtitle="Generated from verified payments only" />
        {invoices.loading ? (
          <div className="p-5">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : invoices.data && invoices.data.invoices.length ? (
          <Table>
            <THead>
              <TR>
                <TH>Number</TH>
                <TH align="right">Total</TH>
                <TH>Status</TH>
                <TH>Period</TH>
                <TH>Paid</TH>
              </TR>
            </THead>
            <TBody>
              {invoices.data.invoices.map((invoice) => (
                <TR key={invoice.id}>
                  <TD mono>{invoice.number}</TD>
                  <TD align="right" mono>
                    {money(invoice.total, invoice.currency, 2)}
                  </TD>
                  <TD>
                    <StatusBadge status={invoice.status} />
                  </TD>
                  <TD>
                    {dateTime(invoice.period_start)} → {dateTime(invoice.period_end)}
                  </TD>
                  <TD>{dateTime(invoice.paid_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState title="No invoices" description="Invoices appear after a verified payment." />
        )}
      </Panel>

      {feeEligible ? (
        <Panel>
          <PanelHeader
            title="Performance fee"
            subtitle="Elite only · realized P&L with a high-water mark"
            action={<Badge tone="warn">legal review required</Badge>}
          />
          <PanelBody className="space-y-3">
            <KeyValue
              items={[
                { label: "Consent", value: fee.data?.consent?.granted ? `Granted ${dateTime(fee.data.consent.granted_at ?? null)}` : "Not granted" },
                { label: "High-water mark", value: fee.data?.high_water_mark != null ? money(fee.data.high_water_mark) : "—", mono: true },
                { label: "Rate", value: fee.data?.terms?.rate_pct != null ? `${fee.data.terms.rate_pct}%` : "—" },
                { label: "Basis", value: fee.data?.terms?.basis ?? "realized P&L only" },
              ]}
            />
            <p className="text-2xs leading-relaxed text-paper-faint">
              {fee.data?.note ??
                "Fees are computed on realized gains above the previous high-water mark, with losses recovered first. No fee is charged on unrealized gains. This module stays disabled until the agreement has been reviewed."}
            </p>
          </PanelBody>
        </Panel>
      ) : null}

      <Dialog
        open={Boolean(selected && checkout)}
        onClose={() => {
          setSelected(null);
          setCheckout(null);
        }}
        title={`Subscribe to ${selected?.name ?? "plan"}`}
        description="The billing provider in this environment is the mock adapter, which exercises the same signed-webhook path as production."
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setSelected(null);
                setCheckout(null);
              }}
            >
              Cancel
            </Button>
            <Button loading={busy} onClick={completeMock}>
              Complete simulated payment
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <KeyValue
            items={[
              { label: "Plan", value: selected?.name ?? "—" },
              { label: "Amount", value: money(selected?.price_monthly ?? 0, selected?.currency ?? "USD", 2), mono: true },
              { label: "Provider", value: checkout?.provider ?? "mock" },
              { label: "Mode", value: checkout?.mode ?? "mock" },
            ]}
          />
          <div className="rounded-lg border border-warn/30 bg-warn/5 px-3 py-2">
            <p className="text-2xs leading-relaxed text-warn">
              No card is charged. This confirms a simulated payment so the webhook and entitlement path can be
              exercised end to end.
            </p>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
