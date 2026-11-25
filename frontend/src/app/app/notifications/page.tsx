"use client";

import * as React from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { relativeTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Tabs } from "@/components/ui/dialog";
import { Panel, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import type { NotificationsResponse } from "@/lib/types";

const SEVERITY_TONE: Record<string, "gain" | "loss" | "warn" | "info" | "neutral"> = {
  info: "info",
  success: "gain",
  warning: "warn",
  critical: "loss",
  error: "loss",
};

export default function NotificationsPage() {
  const toast = useToast();
  const [filter, setFilter] = React.useState("all");
  const notifications = useApi<NotificationsResponse>((signal) => api("/notifications", { signal, query: { limit: 100 } }));
  const [busy, setBusy] = React.useState(false);

  const rows = notifications.data?.notifications ?? [];
  const categories = Array.from(new Set(rows.map((row) => row.category)));
  const filtered = filter === "all" ? rows : rows.filter((row) => row.category === filter);
  const unread = notifications.data?.unread_count ?? 0;

  async function markRead(id: string) {
    try {
      await api(`/notifications/${id}/read`, { method: "POST" });
      notifications.refetch();
    } catch (error) {
      toast.error("Could not mark as read", errorMessage(error));
    }
  }

  async function markAll() {
    setBusy(true);
    try {
      await api("/notifications/read-all", { method: "POST" });
      notifications.refetch();
      toast.success("All notifications marked read");
    } catch (error) {
      toast.error("Could not mark all read", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Activity"
        title="Notifications"
        description="Trade events, risk warnings, connection failures, billing and security notices. A trade notification is only sent after the execution system confirms the fill."
        action={
          <Button size="sm" variant="secondary" onClick={markAll} disabled={busy || unread === 0}>
            Mark all read {unread ? `(${unread})` : ""}
          </Button>
        }
      />

      {notifications.error ? <ErrorNote message={notifications.error} onRetry={notifications.refetch} /> : null}

      <Tabs
        tabs={[
          { id: "all", label: "All", count: rows.length },
          ...categories.map((category) => ({
            id: category,
            label: category.replace(/_/g, " "),
            count: rows.filter((row) => row.category === category).length,
          })),
        ]}
        active={filter}
        onChange={setFilter}
      />

      <Panel>
        <PanelHeader
          title="Feed"
          subtitle={unread ? `${unread} unread` : "Everything read"}
          action={<span className="text-2xs text-paper-faint">Newest first</span>}
        />
        {notifications.loading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : filtered.length ? (
          <ul className="divide-y divide-line-soft/70">
            {filtered.map((item) => (
              <li
                key={item.id}
                className={`flex items-start justify-between gap-4 px-5 py-4 ${item.read_at ? "" : "bg-ink-800/30"}`}
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm text-paper">{item.title}</p>
                    <Badge tone={SEVERITY_TONE[item.severity] ?? "neutral"}>{item.severity}</Badge>
                    <Badge tone="outline">{item.category.replace(/_/g, " ")}</Badge>
                    {item.read_at ? null : <span className="h-1.5 w-1.5 rounded-full bg-champagne-400" />}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-paper-muted">{item.body}</p>
                  <p className="mt-1 text-2xs text-paper-faint">{relativeTime(item.created_at)}</p>
                </div>
                {item.read_at ? null : (
                  <button
                    type="button"
                    onClick={() => markRead(item.id)}
                    className="shrink-0 text-2xs text-paper-faint transition hover:text-paper"
                  >
                    Mark read
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="Nothing here"
            description="Notifications appear when trades fill, risk limits are approached, connections fail or billing changes."
          />
        )}
      </Panel>
    </div>
  );
}
