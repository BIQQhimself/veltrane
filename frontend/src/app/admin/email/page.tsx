"use client";

import * as React from "react";
import { Plus, Send, X } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime, titleCase } from "@/lib/format";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, KeyValue, Skeleton } from "@/components/ui/data";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";

type Stats = {
  window_days: number;
  provider: string;
  delivery_configured: boolean;
  from_address: string;
  sent: number;
  queued: number;
  failed: number;
  bounced: number;
  complained: number;
  suppressed: number;
  delivery_rate: number | null;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  note: string;
};

type Campaign = {
  id: string;
  name: string;
  subject: string;
  template: string;
  audience: string;
  tier: string | null;
  status: string;
  scheduled_at: string | null;
  completed_at: string | null;
  recipients: number;
  sent: number;
  failed: number;
  created_at: string | null;
};

type Centre = {
  stats: Stats;
  campaigns: Campaign[];
  templates: Record<string, string>;
  from_address: string;
  reply_to: string;
};

export default function AdminEmailPage() {
  const toast = useToast();
  const centre = useApi<Centre>((signal) => api("/admin/email", { signal }));
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [subject, setSubject] = React.useState("");
  const [template, setTemplate] = React.useState("announcement");
  const [body, setBody] = React.useState("");
  const [audience, setAudience] = React.useState("all");
  const [tier, setTier] = React.useState("pro");
  const [testEmail, setTestEmail] = React.useState("");
  const [sendNow, setSendNow] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  async function create(event?: React.FormEvent) {
    event?.preventDefault();
    setBusy(true);
    try {
      await api("/admin/email/campaigns", {
        method: "POST",
        body: {
          name,
          subject,
          template,
          body,
          audience,
          tier: audience === "tier" ? tier : null,
          test_email: audience === "test" ? testEmail : null,
          send_now: sendNow,
        },
      });
      toast.success("Campaign created", sendNow ? "Queued for delivery now." : "Saved as a draft. Send it when ready.");
      setOpen(false);
      setName("");
      setSubject("");
      setBody("");
      centre.refetch();
    } catch (error) {
      toast.error("Could not create the campaign", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function send(campaign: Campaign) {
    if (!window.confirm(`Queue “${campaign.name}” for ${campaign.audience === "all" ? "every subscriber" : campaign.audience}?`)) {
      return;
    }
    setBusy(true);
    try {
      const result = await api<{ summary: { queued: number } }>(`/admin/email/campaigns/${campaign.id}/send`, {
        method: "POST",
      });
      toast.success("Campaign queued", `${result.summary?.queued ?? 0} messages queued. Delivery is recorded per message.`);
      centre.refetch();
    } catch (error) {
      toast.error("Send failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function cancel(campaign: Campaign) {
    setBusy(true);
    try {
      await api(`/admin/email/campaigns/${campaign.id}`, { method: "DELETE" });
      toast.info("Campaign cancelled");
      centre.refetch();
    } catch (error) {
      toast.error("Could not cancel", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const stats = centre.data?.stats;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Operations"
        title="Email centre"
        description="Transactional mail and campaigns. Nothing is marked sent until the provider accepts it, and webhook events update the record."
        action={
          <Button size="sm" onClick={() => setOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            New campaign
          </Button>
        }
      />

      {centre.error ? <ErrorNote message={centre.error} onRetry={centre.refetch} /> : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader
            title="Delivery"
            subtitle={stats ? `Last ${stats.window_days} days` : undefined}
            action={<Badge tone={stats?.delivery_configured ? "gain" : "neutral"}>{stats?.provider ?? "—"}</Badge>}
          />
          <PanelBody>
            {centre.loading || !stats ? (
              <Skeleton className="h-40 w-full" />
            ) : (
              <>
                <KeyValue
                  items={[
                    { label: "Sent", value: stats.sent },
                    { label: "Queued", value: stats.queued },
                    { label: "Failed", value: stats.failed },
                    { label: "Bounced", value: stats.bounced },
                    { label: "Suppressed", value: stats.suppressed },
                    {
                      label: "Delivery rate",
                      value: stats.delivery_rate === null ? "—" : `${(stats.delivery_rate * 100).toFixed(1)}%`,
                    },
                  ]}
                />
                <p className="mt-3 text-2xs leading-relaxed text-paper-faint">{stats.note}</p>
              </>
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="By category" />
          <PanelBody className="space-y-2">
            {stats ? (
              Object.entries(stats.by_category).length ? (
                Object.entries(stats.by_category).map(([category, count]) => (
                  <div key={category} className="flex items-center justify-between border-b border-line-soft/60 py-1.5 last:border-0">
                    <span className="text-xs text-paper-muted">{titleCase(category)}</span>
                    <span className="num text-xs text-paper">{count}</span>
                  </div>
                ))
              ) : (
                <p className="text-2xs text-paper-faint">No mail in this window.</p>
              )
            ) : (
              <Skeleton className="h-24 w-full" />
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Sender" subtitle="Configured on the server, not in the browser" />
          <PanelBody>
            {centre.data ? (
              <KeyValue
                items={[
                  { label: "From", value: centre.data.from_address },
                  { label: "Reply-to", value: centre.data.reply_to },
                  { label: "Templates", value: Object.keys(centre.data.templates).join(", ") },
                ]}
              />
            ) : (
              <Skeleton className="h-24 w-full" />
            )}
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Campaigns" subtitle="Drafts stay local until you send them" />
        {centre.loading ? (
          <div className="p-5">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : centre.data?.campaigns.length ? (
          <Table>
            <THead>
              <TR>
                <TH>Campaign</TH>
                <TH>Audience</TH>
                <TH>Status</TH>
                <TH>Queued</TH>
                <TH>Created</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {centre.data.campaigns.map((campaign) => (
                <TR key={campaign.id}>
                  <TD>
                    <p className="text-paper">{campaign.name}</p>
                    <p className="text-2xs text-paper-faint">{campaign.subject}</p>
                  </TD>
                  <TD className="text-paper-muted">
                    {campaign.audience === "tier" ? titleCase(campaign.tier ?? "—") : titleCase(campaign.audience)}
                  </TD>
                  <TD>
                    <StatusBadge status={campaign.status} />
                  </TD>
                  <TD className="num text-paper-muted">
                    {campaign.sent}/{campaign.recipients}
                  </TD>
                  <TD className="text-paper-faint">{dateTime(campaign.created_at)}</TD>
                  <TD>
                    <div className="flex justify-end gap-1.5">
                      {campaign.status === "draft" || campaign.status === "scheduled" ? (
                        <>
                          <Button size="sm" variant="secondary" disabled={busy} onClick={() => send(campaign)}>
                            <Send className="h-3 w-3" />
                            Send
                          </Button>
                          <Button size="sm" variant="ghost" disabled={busy} onClick={() => cancel(campaign)}>
                            <X className="h-3 w-3" />
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState title="No campaigns yet" description="Announcements and maintenance notices are sent from here." />
        )}
      </Panel>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="New campaign"
        description="Promotional mail respects each subscriber's preference and unsubscribe link."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={() => create()}>
              Create
            </Button>
          </>
        }
      >
        <form onSubmit={create} className="space-y-3">
          <Field label="Name" htmlFor="campaign-name" hint="Internal only.">
            <Input id="campaign-name" value={name} onChange={(event) => setName(event.target.value)} required minLength={2} />
          </Field>
          <Field label="Subject" htmlFor="campaign-subject">
            <Input id="campaign-subject" value={subject} onChange={(event) => setSubject(event.target.value)} required />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Template" htmlFor="campaign-template">
              <Select id="campaign-template" value={template} onChange={(event) => setTemplate(event.target.value)}>
                {Object.entries(centre.data?.templates ?? { announcement: "Announcement" }).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Audience" htmlFor="campaign-audience">
              <Select id="campaign-audience" value={audience} onChange={(event) => setAudience(event.target.value)}>
                <option value="all">All active subscribers</option>
                <option value="tier">One plan</option>
                <option value="test">A single test address</option>
              </Select>
            </Field>
          </div>
          {audience === "tier" ? (
            <Field label="Plan" htmlFor="campaign-tier">
              <Select id="campaign-tier" value={tier} onChange={(event) => setTier(event.target.value)}>
                {["free", "basic", "pro", "elite"].map((code) => (
                  <option key={code} value={code}>
                    {titleCase(code)}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}
          {audience === "test" ? (
            <Field label="Test address" htmlFor="campaign-test">
              <Input
                id="campaign-test"
                type="email"
                value={testEmail}
                onChange={(event) => setTestEmail(event.target.value)}
                required
              />
            </Field>
          ) : null}
          <Field label="Body" htmlFor="campaign-body" hint="Plain text. Line breaks become paragraphs.">
            <Textarea
              id="campaign-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              className="min-h-28"
            />
          </Field>
          <label className="flex items-start gap-2.5 text-2xs leading-relaxed text-paper-muted">
            <input
              type="checkbox"
              checked={sendNow}
              onChange={(event) => setSendNow(event.target.checked)}
              className="mt-0.5 h-3.5 w-3.5 accent-champagne-500"
            />
            Queue for delivery immediately. Leave off to keep it as a draft you send from the table.
          </label>
        </form>
      </Dialog>
    </div>
  );
}
