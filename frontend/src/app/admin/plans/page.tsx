"use client";

import * as React from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { money, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorNote, Skeleton } from "@/components/ui/data";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Panel, PanelHeader, SectionHeading } from "@/components/ui/panel";
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
  is_active: boolean;
  trial_days: number;
};

export default function AdminPlansPage() {
  const toast = useToast();
  const plans = useApi<{ plans: Plan[]; editable: string[] }>((signal) => api("/admin/plans", { signal }));
  const [target, setTarget] = React.useState<Plan | null>(null);
  const [price, setPrice] = React.useState("0");
  const [tagline, setTagline] = React.useState("");
  const [maxConnections, setMaxConnections] = React.useState("");
  const [maxPositions, setMaxPositions] = React.useState("");
  const [maxDemo, setMaxDemo] = React.useState("");
  const [maxBacktests, setMaxBacktests] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  function open(plan: Plan) {
    setTarget(plan);
    setPrice(String(plan.price_monthly));
    setTagline(plan.tagline ?? "");
    setMaxConnections(String(plan.limits.max_connections ?? ""));
    setMaxPositions(String(plan.limits.max_open_positions ?? ""));
    setMaxDemo(String(plan.limits.max_daily_demo_executions ?? ""));
    setMaxBacktests(String(plan.limits.max_backtests_per_day ?? ""));
  }

  async function save() {
    if (!target) return;
    setBusy(true);
    try {
      await api(`/admin/plans/${target.code}`, {
        method: "PATCH",
        body: {
          price_monthly: Number(price),
          tagline,
          limits: {
            max_connections: maxConnections === "" ? null : Number(maxConnections),
            max_open_positions: maxPositions === "" ? null : Number(maxPositions),
            max_daily_demo_executions: maxDemo === "" ? null : Number(maxDemo),
            max_backtests_per_day: maxBacktests === "" ? null : Number(maxBacktests),
          },
        },
      });
      toast.success("Plan updated", "New subscriptions use the new figures. Existing entitlements re-resolve server-side.");
      setTarget(null);
      plans.refetch();
    } catch (error) {
      toast.error("Update failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Commercial"
        title="Plans & entitlements"
        description="Prices and limits are configuration, not code. Empty limit means unlimited; the risk engine still caps exposure."
      />

      {plans.error ? <ErrorNote message={plans.error} onRetry={plans.refetch} /> : null}

      <Panel>
        <PanelHeader title="Plans" subtitle="Seeded defaults may be replaced by the operator" />
        {plans.loading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Plan</TH>
                <TH align="right">Price</TH>
                <TH align="right">Connections</TH>
                <TH align="right">Positions</TH>
                <TH align="right">Demo / day</TH>
                <TH align="right">Backtests / day</TH>
                <TH>State</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {(plans.data?.plans ?? []).map((plan) => (
                <TR key={plan.code} onClick={() => open(plan)}>
                  <TD>
                    <div>
                      <p className="text-xs text-paper">{plan.name}</p>
                      <p className="text-2xs text-paper-faint">{plan.tagline}</p>
                    </div>
                  </TD>
                  <TD align="right" mono>
                    {money(plan.price_monthly, plan.currency, 0)}
                  </TD>
                  <TD align="right" mono>
                    {plan.limits.max_connections ?? "∞"}
                  </TD>
                  <TD align="right" mono>
                    {plan.limits.max_open_positions ?? "∞"}
                  </TD>
                  <TD align="right" mono>
                    {plan.limits.max_daily_demo_executions ?? "∞"}
                  </TD>
                  <TD align="right" mono>
                    {plan.limits.max_backtests_per_day ?? "∞"}
                  </TD>
                  <TD>
                    <Badge tone={plan.is_active ? "gain" : "neutral"}>{plan.is_active ? "active" : "hidden"}</Badge>
                  </TD>
                  <TD align="right">
                    <span className="text-2xs text-paper-faint">Edit</span>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>

      <Panel>
        <PanelHeader title="Features by plan" subtitle="Capability flags resolved server-side" />
        <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
          {(plans.data?.plans ?? []).map((plan) => (
            <div key={plan.code} className="rounded-lg border border-line-soft p-3">
              <p className="text-xs text-paper">{titleCase(plan.code)}</p>
              <ul className="mt-2 space-y-1">
                {(plan.features ?? []).map((feature) => (
                  <li key={feature} className="text-2xs leading-relaxed text-paper-faint">
                    · {feature}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Panel>

      <Dialog
        open={Boolean(target)}
        onClose={() => setTarget(null)}
        title={`Edit ${target?.name ?? "plan"}`}
        description="Changes take effect for entitlement resolution immediately and are audited."
        footer={
          <>
            <Button variant="ghost" onClick={() => setTarget(null)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={save}>
              Save plan
            </Button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Monthly price" htmlFor="price">
            <Input id="price" type="number" min="0" step="1" value={price} onChange={(event) => setPrice(event.target.value)} />
          </Field>
          <Field label="Tagline" htmlFor="tagline">
            <Input id="tagline" value={tagline} onChange={(event) => setTagline(event.target.value)} />
          </Field>
          <Field label="Max connections" htmlFor="conn" hint="Empty = unlimited">
            <Input id="conn" type="number" min="0" value={maxConnections} onChange={(event) => setMaxConnections(event.target.value)} />
          </Field>
          <Field label="Max open positions" htmlFor="pos" hint="Empty = unlimited">
            <Input id="pos" type="number" min="0" value={maxPositions} onChange={(event) => setMaxPositions(event.target.value)} />
          </Field>
          <Field label="Demo executions / day" htmlFor="demo" hint="Empty = unlimited">
            <Input id="demo" type="number" min="0" value={maxDemo} onChange={(event) => setMaxDemo(event.target.value)} />
          </Field>
          <Field label="Backtests / day" htmlFor="bt" hint="Empty = unlimited">
            <Input id="bt" type="number" min="0" value={maxBacktests} onChange={(event) => setMaxBacktests(event.target.value)} />
          </Field>
        </div>
      </Dialog>
    </div>
  );
}
