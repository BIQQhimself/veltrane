"use client";

import * as React from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Field, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { Tabs } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";

type Message = { role: string; message: string; at: string; staff_email?: string };
type Ticket = {
  id: string;
  org_id: string;
  subject: string;
  status: string;
  priority: string;
  messages: Message[];
  created_at: string;
};

export default function AdminSupportPage() {
  const toast = useToast();
  const [filter, setFilter] = React.useState("all");
  const tickets = useApi<{ tickets: Ticket[] }>((signal) => api("/admin/support/tickets", { signal }));
  const [target, setTarget] = React.useState<Ticket | null>(null);
  const [reply, setReply] = React.useState("");
  const [status, setStatus] = React.useState("open");
  const [busy, setBusy] = React.useState(false);

  const rows = tickets.data?.tickets ?? [];
  const filtered = filter === "all" ? rows : rows.filter((ticket) => ticket.status === filter);

  function open(ticket: Ticket) {
    setTarget(ticket);
    setStatus(ticket.status);
    setReply("");
  }

  async function send() {
    if (!target) return;
    setBusy(true);
    try {
      await api(`/admin/support/tickets/${target.id}/reply`, {
        method: "POST",
        body: { message: reply, status },
      });
      toast.success("Reply recorded");
      setTarget(null);
      tickets.refetch();
    } catch (error) {
      toast.error("Reply failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Service"
        title="Support"
        description="Subscriber tickets. Replies are recorded with your staff identity; never ask a subscriber to send API secrets."
        action={<Badge tone="gold">{rows.filter((ticket) => ticket.status === "open").length} open</Badge>}
      />

      <Tabs
        tabs={[
          { id: "all", label: "All", count: rows.length },
          { id: "open", label: "Open", count: rows.filter((t) => t.status === "open").length },
          { id: "pending", label: "Pending", count: rows.filter((t) => t.status === "pending").length },
          { id: "resolved", label: "Resolved", count: rows.filter((t) => t.status === "resolved").length },
        ]}
        active={filter}
        onChange={setFilter}
      />

      {tickets.error ? <ErrorNote message={tickets.error} onRetry={tickets.refetch} /> : null}

      <Panel>
        <PanelHeader title="Tickets" subtitle="Newest first" />
        {tickets.loading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : filtered.length ? (
          <ul className="divide-y divide-line-soft/70">
            {filtered.map((ticket) => (
              <li key={ticket.id}>
                <button
                  type="button"
                  onClick={() => open(ticket)}
                  className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left transition hover:bg-ink-800/60"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm text-paper">{ticket.subject}</p>
                      <StatusBadge status={ticket.status} />
                      <Badge tone={ticket.priority === "high" || ticket.priority === "urgent" ? "loss" : "outline"}>
                        {ticket.priority}
                      </Badge>
                    </div>
                    <p className="mt-1 truncate text-2xs text-paper-faint">
                      {ticket.messages?.[ticket.messages.length - 1]?.message ?? "No messages"}
                    </p>
                  </div>
                  <span className="shrink-0 text-2xs text-paper-faint">{dateTime(ticket.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No tickets" description="Subscriber tickets raised in the workspace appear here." />
        )}
      </Panel>

      <Dialog
        open={Boolean(target)}
        onClose={() => setTarget(null)}
        title={target?.subject ?? "Ticket"}
        description={target ? `Organisation ${target.org_id.slice(0, 8)}` : undefined}
        wide
        footer={
          <>
            <Button variant="ghost" onClick={() => setTarget(null)}>
              Close
            </Button>
            <Button loading={busy} onClick={send} disabled={reply.trim().length === 0}>
              Send reply
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <ul className="space-y-2">
            {(target?.messages ?? []).map((message, index) => (
              <li
                key={index}
                className={`rounded-lg border px-3 py-2 ${
                  message.role === "staff" ? "border-champagne-600/30 bg-champagne-500/[0.05]" : "border-line-soft"
                }`}
              >
                <p className="text-2xs uppercase tracking-label text-paper-faint">
                  {message.role === "staff" ? `Staff · ${message.staff_email ?? ""}` : "Subscriber"} ·{" "}
                  {dateTime(message.at)}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-paper-muted">{message.message}</p>
              </li>
            ))}
          </ul>
          <Field label="Reply" htmlFor="reply">
            <Textarea id="reply" value={reply} onChange={(event) => setReply(event.target.value)} className="min-h-24" />
          </Field>
          <Field label="Set status" htmlFor="ticket_status">
            <Select id="ticket_status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="open">Open</option>
              <option value="pending">Pending</option>
              <option value="resolved">Resolved</option>
            </Select>
          </Field>
          <p className="text-2xs leading-relaxed text-paper-faint">
            Never request API keys, secrets or passwords. If a credential may be exposed, instruct the subscriber to
            revoke it at the venue and rotate it in Connected accounts.
          </p>
        </div>
      </Dialog>
    </div>
  );
}
