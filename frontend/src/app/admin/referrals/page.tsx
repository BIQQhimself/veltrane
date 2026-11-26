"use client";

import * as React from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime, money, number, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, KeyValue, Skeleton } from "@/components/ui/data";
import { Field, Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";

type Funnel = {
  window_days: number;
  unique_visitors: number;
  clicks: number;
  registrations: number;
  oauth_starts: number;
  connections: number;
  verified_conversions: number;
  verified_commission: number;
  estimated_conversions: number;
  click_to_registration: number | null;
  registration_to_connection: number | null;
  note: string;
};

type Event = {
  id: string;
  kind: string;
  status: string;
  visitor_id: string | null;
  user_id: string | null;
  connection_id: string | null;
  created_at: string | null;
};

type Overview = {
  link: { url: string; campaign: string; token: string; enabled: boolean; updated_at: string | null };
  funnel: Funnel;
  plan_mix: { plan: string; accounts: number }[];
  recent_events: Event[];
  templates: { tracking_params: string[] };
};

function rate(value: number | null): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
}

export default function AdminReferralsPage() {
  const toast = useToast();
  const overview = useApi<Overview>((signal) => api("/admin/referrals", { signal }));
  const [url, setUrl] = React.useState("");
  const [campaign, setCampaign] = React.useState("veltrane");
  const [enabled, setEnabled] = React.useState(true);
  const [userId, setUserId] = React.useState("");
  const [amount, setAmount] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (overview.data) {
      setUrl(overview.data.link.url);
      setCampaign(overview.data.link.campaign);
      setEnabled(overview.data.link.enabled);
    }
  }, [overview.data]);

  async function saveLink(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/admin/referrals/link", { method: "PUT", body: { url, campaign, enabled } });
      toast.success("Referral link saved", "The link must carry a Deriv tracking parameter.");
      overview.refetch();
    } catch (error) {
      toast.error("Could not save the link", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function recordConversion(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/admin/referrals/conversions", {
        method: "POST",
        body: {
          user_id: userId,
          amount: Number(amount),
          currency: "USD",
          note: "Recorded from the Deriv partner statement",
        },
      });
      toast.success("Verified conversion recorded", "Only operator-confirmed figures count as commission.");
      setUserId("");
      setAmount("");
      overview.refetch();
    } catch (error) {
      toast.error("Could not record the conversion", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const data = overview.data;
  const funnel = data?.funnel;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Growth"
        title="Deriv referrals"
        description="Only what VELTRANE can observe itself is measured here. Commission counts only when an operator records a verified figure from Deriv."
        action={<Badge tone={data?.link.enabled ? "gain" : "neutral"}>{data?.link.enabled ? "live" : "off"}</Badge>}
      />

      {overview.error ? <ErrorNote message={overview.error} onRetry={overview.refetch} /> : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader title="Funnel" subtitle={funnel ? `Last ${funnel.window_days} days` : undefined} />
          <PanelBody>
            {overview.loading || !funnel ? (
              <Skeleton className="h-40 w-full" />
            ) : (
              <KeyValue
                items={[
                  { label: "Unique visitors", value: number(funnel.unique_visitors, 0) },
                  { label: "Clicks", value: number(funnel.clicks, 0) },
                  { label: "Registrations", value: number(funnel.registrations, 0) },
                  { label: "OAuth starts", value: number(funnel.oauth_starts, 0) },
                  { label: "Connections", value: number(funnel.connections, 0) },
                  { label: "Click → registration", value: rate(funnel.click_to_registration) },
                  { label: "Registration → connection", value: rate(funnel.registration_to_connection) },
                ]}
              />
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Commission" subtitle="Verified by a human, never inferred" />
          <PanelBody>
            {funnel ? (
              <>
                <p className="font-display text-3xl text-paper">{money(funnel.verified_commission)}</p>
                <p className="mt-1 text-2xs text-paper-faint">
                  {funnel.verified_conversions} verified · {funnel.estimated_conversions} unverified
                </p>
                <p className="mt-3 text-2xs leading-relaxed text-paper-faint">{funnel.note}</p>
              </>
            ) : (
              <Skeleton className="h-24 w-full" />
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Referred accounts by plan" />
          <PanelBody className="space-y-2">
            {data?.plan_mix.length ? (
              data.plan_mix.map((row) => (
                <div
                  key={row.plan}
                  className="flex items-center justify-between border-b border-line-soft/60 py-1.5 last:border-0"
                >
                  <span className="text-xs text-paper-muted">{titleCase(row.plan)}</span>
                  <span className="num text-xs text-paper">{row.accounts}</span>
                </div>
              ))
            ) : (
              <p className="text-2xs text-paper-faint">No referred accounts yet.</p>
            )}
          </PanelBody>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Referral link" subtitle="HTTPS only, with a Deriv tracking parameter" />
          <PanelBody>
            <form onSubmit={saveLink} className="space-y-3">
              <Field
                label="Link"
                htmlFor="referral-url"
                hint={`Accepted parameters: ${data?.templates.tracking_params.join(", ") ?? "t, affiliate_token, sidi, ca"}`}
              >
                <Input
                  id="referral-url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://t.deriv.link/?t=..."
                />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Campaign" htmlFor="referral-campaign">
                  <Input id="referral-campaign" value={campaign} onChange={(event) => setCampaign(event.target.value)} />
                </Field>
                <label className="flex items-end gap-2 pb-2 text-xs text-paper-muted">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(event) => setEnabled(event.target.checked)}
                    className="h-3.5 w-3.5 accent-champagne-500"
                  />
                  Enabled
                </label>
              </div>
              <div className="flex items-center justify-between gap-2">
                <p className="text-2xs text-paper-faint">
                  Token {data?.link.token ? <span className="num">{data.link.token}</span> : "not detected"}
                </p>
                <Button type="submit" size="sm" loading={busy}>
                  Save link
                </Button>
              </div>
            </form>
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader
            title="Record a verified conversion"
            subtitle="Copy the figure from the Deriv partner statement"
          />
          <PanelBody>
            <form onSubmit={recordConversion} className="space-y-3">
              <Field label="Subscriber id" htmlFor="conversion-user">
                <Input
                  id="conversion-user"
                  value={userId}
                  onChange={(event) => setUserId(event.target.value)}
                  placeholder="uuid"
                  required
                />
              </Field>
              <Field label="Commission (USD)" htmlFor="conversion-amount">
                <Input
                  id="conversion-amount"
                  value={amount}
                  inputMode="decimal"
                  onChange={(event) => setAmount(event.target.value)}
                  required
                />
              </Field>
              <div className="flex justify-end">
                <Button type="submit" size="sm" variant="secondary" loading={busy}>
                  Record conversion
                </Button>
              </div>
            </form>
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Recent referral events" subtitle="Newest first" />
        {overview.loading ? (
          <div className="p-5">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : data?.recent_events.length ? (
          <Table>
            <THead>
              <TR>
                <TH>When</TH>
                <TH>Event</TH>
                <TH>Status</TH>
                <TH>Visitor</TH>
                <TH>Subscriber</TH>
              </TR>
            </THead>
            <TBody>
              {data.recent_events.map((event) => (
                <TR key={event.id}>
                  <TD className="text-paper-faint">{dateTime(event.created_at)}</TD>
                  <TD>{titleCase(event.kind)}</TD>
                  <TD>
                    <Badge tone={event.status === "verified" ? "gain" : "outline"}>{event.status}</Badge>
                  </TD>
                  <TD className="num text-paper-faint">{event.visitor_id ?? "—"}</TD>
                  <TD className="num text-paper-faint">{event.user_id ? event.user_id.slice(0, 8) : "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState title="No referral activity yet" description="Clicks appear here as soon as the link is used." />
        )}
      </Panel>
    </div>
  );
}
