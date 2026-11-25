"use client";

import * as React from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Input } from "@/components/ui/input";
import { Panel, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";

type Entry = {
  id: string;
  org_id: string | null;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
};

export default function AdminAuditPage() {
  const [action, setAction] = React.useState("");
  const [applied, setApplied] = React.useState("");
  const log = useApi<{ entries: Entry[] }>((signal) =>
    api("/admin/audit", { signal, query: { action: applied || undefined, limit: 200 } }),
  );

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Forensics"
        title="Audit log"
        description="Append-only record of privileged and security-relevant actions. Entries are not editable from this interface."
        action={<Badge tone="gold">{log.data?.entries.length ?? 0} entries</Badge>}
      />

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied(action.trim());
        }}
      >
        <Input
          value={action}
          onChange={(event) => setAction(event.target.value)}
          placeholder="Filter by action, e.g. risk_policy_updated"
          aria-label="Filter audit log by action"
        />
        <Button type="submit" variant="secondary">
          Filter
        </Button>
      </form>

      {log.error ? <ErrorNote message={log.error} onRetry={log.refetch} /> : null}

      <Panel>
        <PanelHeader title="Entries" subtitle="Newest first" />
        {log.loading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : log.data && log.data.entries.length ? (
          <Table>
            <THead>
              <TR>
                <TH>Action</TH>
                <TH>Actor</TH>
                <TH>Target</TH>
                <TH>IP</TH>
                <TH>When</TH>
              </TR>
            </THead>
            <TBody>
              {log.data.entries.map((entry) => (
                <TR key={entry.id}>
                  <TD>
                    <div>
                      <p className="num text-xs text-paper">{entry.action}</p>
                      {entry.meta ? (
                        <p className="max-w-[22rem] truncate text-2xs text-paper-faint" title={JSON.stringify(entry.meta)}>
                          {JSON.stringify(entry.meta)}
                        </p>
                      ) : null}
                    </div>
                  </TD>
                  <TD>
                    <div>
                      <p className="text-xs text-paper-muted">{entry.actor_email ?? "system"}</p>
                      <p className="text-2xs text-paper-faint">{entry.actor_role ?? "—"}</p>
                    </div>
                  </TD>
                  <TD>
                    <p className="text-2xs text-paper-muted">{entry.target_type ?? "—"}</p>
                    <p className="num text-2xs text-paper-faint">{(entry.target_id ?? "").slice(0, 12) || "—"}</p>
                  </TD>
                  <TD mono>{entry.ip ?? "—"}</TD>
                  <TD>{dateTime(entry.created_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState title="No entries" description="Audited actions appear here as they happen." />
        )}
      </Panel>
    </div>
  );
}
