"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { money, percent, titleCase } from "@/lib/format";
import { AreaChart, BarList } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import { ErrorNote, KeyValue, Skeleton, Stat } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import type { AdminOverview } from "@/lib/types";

type Revenue = {
  series: Array<{ date: string; amount: number }>;
  breakdown: Array<{ code: string; name: string; price_monthly: number; subscribers: number; mrr: number }>;
  overview: AdminOverview;
};

type Health = {
  database: { ok: boolean };
  redis: { ok: boolean; note: string };
  live_trading_enabled: boolean;
  billing_provider: string;
  market_data_source: string;
  providers: Array<{ code: string; name: string; status: string }>;
  queued_emails: number;
  email_delivery: string;
  version: string;
};

type Costs = { costs?: Record<string, number>; total_monthly?: number; note?: string };

export default function AdminOverviewPage() {
  const overview = useApi<AdminOverview>((signal) => api("/admin/overview", { signal }));
  const revenue = useApi<Revenue>((signal) => api("/admin/revenue", { signal }));
  const health = useApi<Health>((signal) => api("/admin/system/health", { signal }));
  const costs = useApi<Costs>((signal) => api("/admin/costs", { signal }));
  const data = overview.data;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Operator"
        title="Business overview"
        description="Revenue, retention and unit economics from stored records. Cost inputs come from the operator; an unset input is zero, not free."
        action={<Badge tone="gold">{overview.data?.window_days ?? 30}-day window</Badge>}
      />

      {overview.error ? <ErrorNote message={overview.error} onRetry={overview.refetch} /> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {overview.loading || !data ? (
          <>
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
          </>
        ) : (
          <>
            <Stat label="MRR" value={money(data.mrr)} hint={`ARR ${money(data.arr)}`} />
            <Stat label="Paid subscribers" value={`${data.paid_subscribers}`} hint={`${data.organizations} organisations`} />
            <Stat
              label="Free → paid"
              value={percent(data.free_to_paid_conversion_pct, 1)}
              hint={`churn ${percent(data.churn_rate_pct, 1)}`}
            />
            <Stat
              label="Contribution margin"
              value={money(data.contribution_margin)}
              tone={data.contribution_margin >= 0 ? "gain" : "loss"}
              hint={`${percent(data.contribution_margin_pct, 1)} of MRR`}
            />
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <Panel>
          <PanelHeader title="Payments collected" subtitle="Verified provider payments only" />
          <PanelBody>
            {revenue.loading ? (
              <Skeleton className="h-40 w-full" />
            ) : revenue.data && revenue.data.series.length > 1 ? (
              <AreaChart
                values={revenue.data.series.map((point) => point.amount)}
                labels={[revenue.data.series[0]!.date, revenue.data.series[revenue.data.series.length - 1]!.date]}
                ariaLabel="Payments collected over time"
              />
            ) : (
              <p className="py-10 text-center text-xs text-paper-faint">
                No payments in this window. Figures are not interpolated.
              </p>
            )}
            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line-soft pt-4 sm:grid-cols-4">
              {[
                ["Collected", money(data?.payments_collected ?? 0)],
                ["Refunds", money(data?.refunds ?? 0)],
                ["Failures", `${data?.payment_failures ?? 0}`],
                ["Perf. fees", money(data?.performance_fee_revenue ?? 0)],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <p className="label">{label}</p>
                  <p className="num mt-1 text-sm text-paper">{value}</p>
                </div>
              ))}
            </div>
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Revenue by tier" subtitle="Monthly recurring" />
          <PanelBody>
            {revenue.loading ? (
              <Skeleton className="h-40 w-full" />
            ) : revenue.data && revenue.data.breakdown.length ? (
              <BarList
                items={revenue.data.breakdown.map((row) => ({ label: `${row.name} (${row.subscribers})`, value: row.mrr }))}
              />
            ) : (
              <p className="py-10 text-center text-xs text-paper-faint">No active subscriptions.</p>
            )}
          </PanelBody>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader title="Unit economics" subtitle="Per paid subscriber" />
          <PanelBody>
            <KeyValue
              items={[
                { label: "AI cost", value: money(data?.ai_cost_per_subscriber ?? 0, "USD", 2), mono: true },
                { label: "Infrastructure", value: money(data?.infra_cost_per_subscriber ?? 0, "USD", 2), mono: true },
                { label: "Support", value: money(data?.support_cost_per_subscriber ?? 0, "USD", 2), mono: true },
                { label: "AI cost (total)", value: money(data?.ai_cost ?? 0), mono: true },
              ]}
            />
            <p className="mt-3 text-2xs leading-relaxed text-paper-faint">{data?.note}</p>
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Activity" subtitle="This window" />
          <PanelBody>
            <KeyValue
              items={[
                { label: "New subscriptions", value: `${data?.new_subscriptions ?? 0}`, mono: true },
                { label: "Cancellations", value: `${data?.cancellations ?? 0}`, mono: true },
                { label: "Demo executions", value: `${data?.demo_executions ?? 0}`, mono: true },
                { label: "Live trades", value: `${data?.live_trades ?? 0}`, mono: true },
                { label: "Open tickets", value: `${data?.open_support_tickets ?? 0}`, mono: true },
                { label: "Active users", value: `${data?.active_users ?? 0}`, mono: true },
              ]}
            />
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="System" subtitle={health.data ? `v${health.data.version}` : undefined} />
          <PanelBody>
            {health.loading ? (
              <Skeleton className="h-32 w-full" />
            ) : health.data ? (
              <div className="space-y-3">
                <Row label="Database" ok={health.data.database.ok} />
                <Row label="Redis" ok={health.data.redis.ok} note={health.data.redis.ok ? undefined : "degraded"} />
                <div className="flex items-center justify-between text-xs">
                  <span className="text-paper-muted">Live execution</span>
                  <Badge tone={health.data.live_trading_enabled ? "warn" : "neutral"}>
                    {health.data.live_trading_enabled ? "enabled" : "disabled"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-paper-muted">Billing provider</span>
                  <span className="text-paper">{titleCase(health.data.billing_provider)}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-paper-muted">Market data</span>
                  <span className="text-paper">{titleCase(health.data.market_data_source)}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-paper-muted">Queued emails</span>
                  <span className="num text-paper">{health.data.queued_emails}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-paper-muted">Email delivery</span>
                  <span className="text-paper">{health.data.email_delivery}</span>
                </div>
              </div>
            ) : null}
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Provider readiness" subtitle="Literal status values" />
        <PanelBody>
          <div className="grid gap-2 sm:grid-cols-2">
            {(health.data?.providers ?? []).map((provider) => (
              <div key={provider.code} className="flex items-center justify-between rounded-lg border border-line-soft px-3 py-2">
                <span className="text-xs text-paper-muted">{provider.name}</span>
                <Badge tone={provider.status.includes("verified") ? "gain" : provider.status === "simulated" ? "info" : "warn"}>
                  {provider.status.replace(/_/g, " ")}
                </Badge>
              </div>
            ))}
          </div>
        </PanelBody>
      </Panel>

      {costs.data ? (
        <Panel>
          <PanelHeader title="Cost inputs" subtitle="Operator-provided" />
          <PanelBody>
            <KeyValue
              items={Object.entries(costs.data.costs ?? {}).map(([key, value]) => ({
                label: key.replace(/_/g, " "),
                value: money(value, "USD", 2),
                mono: true,
              }))}
            />
            <p className="mt-3 text-2xs text-paper-faint">{costs.data.note}</p>
          </PanelBody>
        </Panel>
      ) : null}
    </div>
  );
}

function Row({ label, ok, note }: { label: string; ok: boolean; note?: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-paper-muted">{label}</span>
      <Badge tone={ok ? "gain" : "warn"}>{ok ? "ok" : note ?? "degraded"}</Badge>
    </div>
  );
}
