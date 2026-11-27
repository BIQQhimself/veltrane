"use client";

import * as React from "react";
import { LifeBuoy, Send } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime, titleCase } from "@/lib/format";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import type { SupportTicket } from "@/lib/types";
import { cn } from "@/lib/cn";

export default function SupportPage() {
  const toast = useToast();
  const tickets = useApi<{ tickets: SupportTicket[] }>((signal) => api("/support/tickets", { signal }));
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [priority, setPriority] = React.useState("normal");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [reply, setReply] = React.useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/support/tickets", { method: "POST", body: { subject, body, priority } });
      toast.success("Ticket opened", "Support will reply by email and in this thread.");
      setSubject("");
      setBody("");
      setPriority("normal");
      tickets.refetch();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function sendReply(ticketId: string) {
    if (reply.trim().length < 2) return;
    setBusy(true);
    try {
      await api(`/support/tickets/${ticketId}/messages`, { method: "POST", body: { message: reply } });
      setReply("");
      tickets.refetch();
    } catch (err) {
      toast.error("Message not sent", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Support"
        title="Talk to a human"
        description="Tickets are answered by the VELTRANE team. Never paste an API secret, password or card number into a ticket — we will never ask for one."
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
        <section className="tile p-5" aria-label="Open a ticket">
          <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
            <LifeBuoy className="h-4 w-4 text-electric-300" aria-hidden />
            New ticket
          </h2>
          <form onSubmit={submit} className="mt-4 space-y-3">
            <Field label="Subject" htmlFor="subject">
              <Input
                id="subject"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                minLength={3}
                maxLength={200}
                placeholder="Deriv session drops after an hour"
                required
              />
            </Field>
            <Field label="What happened?" htmlFor="body" hint="Include what you expected and what you saw.">
              <Textarea
                id="body"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                minLength={5}
                maxLength={4000}
                required
              />
            </Field>
            <Field label="Priority" htmlFor="priority">
              <Select id="priority" value={priority} onChange={(event) => setPriority(event.target.value)}>
                <option value="low">Low — question</option>
                <option value="normal">Normal</option>
                <option value="high">High — trading affected</option>
                <option value="urgent">Urgent — possible account risk</option>
              </Select>
            </Field>
            {error ? <p className="text-xs text-loss">{error}</p> : null}
            <Button type="submit" loading={busy}>
              Open ticket
            </Button>
          </form>
          <p className="mt-4 text-3xs leading-relaxed text-paper-faint">
            If you believe your exchange key is exposed, revoke it at the provider first. We cannot revoke it for you —
            we never hold withdrawal permission or the ability to change your venue credentials.
          </p>
        </section>

        <section className="tile" aria-label="Your tickets">
          <div className="panel-header">
            <h2 className="text-sm font-medium text-paper">Your tickets</h2>
            <Badge tone="neutral">{tickets.data?.tickets.length ?? 0}</Badge>
          </div>
          {tickets.error ? <div className="p-5"><ErrorNote message={tickets.error} onRetry={tickets.refetch} /></div> : null}
          {tickets.loading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          ) : (tickets.data?.tickets.length ?? 0) === 0 ? (
            <div className="p-5">
              <EmptyState title="No tickets yet" description="Anything you open appears here with its full history." />
            </div>
          ) : (
            <ul className="divide-y divide-line-soft">
              {tickets.data?.tickets.map((ticket) => {
                const open = openId === ticket.id;
                return (
                  <li key={ticket.id} className="px-5 py-4">
                    <button
                      type="button"
                      onClick={() => setOpenId(open ? null : ticket.id)}
                      aria-expanded={open}
                      className="flex w-full items-start justify-between gap-3 text-left"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-xs text-paper">{ticket.subject}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-1.5">
                          <StatusBadge status={ticket.status} />
                          <Badge tone={ticket.priority === "urgent" || ticket.priority === "high" ? "warn" : "neutral"}>
                            {titleCase(ticket.priority)}
                          </Badge>
                          <span className="text-3xs text-paper-faint">{dateTime(ticket.created_at)}</span>
                        </span>
                      </span>
                      <span className="text-3xs text-paper-faint">{open ? "Hide" : "Open"}</span>
                    </button>

                    {open ? (
                      <div className="mt-3 space-y-2">
                        {ticket.messages.map((message, index) => (
                          <div
                            key={`${ticket.id}-${index}`}
                            className={cn(
                              "rounded-lg border p-2.5 text-2xs",
                              message.role === "staff"
                                ? "border-electric-500/25 bg-electric-500/[0.06] text-paper"
                                : "border-line-soft bg-obsidian-900/60 text-paper-muted",
                            )}
                          >
                            <p className="mb-1 text-3xs uppercase tracking-label text-paper-faint">
                              {message.role === "staff" ? "VELTRANE support" : "You"} · {dateTime(message.at)}
                            </p>
                            <p className="whitespace-pre-wrap leading-relaxed">{message.message}</p>
                          </div>
                        ))}
                        <div className="flex gap-2">
                          <Input
                            value={reply}
                            onChange={(event) => setReply(event.target.value)}
                            placeholder="Add a message…"
                            aria-label="Reply to this ticket"
                          />
                          <Button variant="secondary" onClick={() => sendReply(ticket.id)} loading={busy}>
                            <Send className="h-3.5 w-3.5" aria-hidden />
                          </Button>
                        </div>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
