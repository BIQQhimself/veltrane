"use client";

import * as React from "react";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime, titleCase } from "@/lib/format";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";

type AdminUser = {
  id: string;
  email: string;
  full_name: string;
  status: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  is_staff: boolean;
  staff_role: string | null;
  org_name: string | null;
  plan_code: string;
  subscription_status: string | null;
  last_login_at: string | null;
  created_at: string;
};

export default function AdminUsersPage() {
  const toast = useToast();
  const [query, setQuery] = React.useState("");
  const [applied, setApplied] = React.useState("");
  const users = useApi<{ users: AdminUser[]; count: number }>((signal) =>
    api("/admin/users", { signal, query: { query: applied || undefined, limit: 100 } }),
  );
  const [target, setTarget] = React.useState<AdminUser | null>(null);
  const [status, setStatus] = React.useState("active");
  const [role, setRole] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  function open(user: AdminUser) {
    setTarget(user);
    setStatus(user.status);
    setRole(user.staff_role ?? "");
    setReason("");
  }

  async function save() {
    if (!target) return;
    setBusy(true);
    try {
      await api(`/admin/users/${target.id}`, {
        method: "PATCH",
        body: {
          status,
          staff_role: role || null,
          is_staff: role ? true : undefined,
          reason: reason || "Administrative change",
        },
      });
      toast.success("User updated", "The change is recorded in the audit log.");
      setTarget(null);
      users.refetch();
    } catch (error) {
      toast.error("Update failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="People"
        title="Users"
        description="Account status, plan and staff role. Credentials and connection secrets are never visible here."
        action={<Badge tone="gold">{users.data?.count ?? 0} shown</Badge>}
      />

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied(query.trim());
        }}
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-paper-faint" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by email or name"
            className="pl-9"
            aria-label="Search users"
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>

      {users.error ? <ErrorNote message={users.error} onRetry={users.refetch} /> : null}

      <Panel>
        <PanelHeader title="Accounts" subtitle="Newest first" />
        {users.loading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : users.data && users.data.users.length ? (
          <Table>
            <THead>
              <TR>
                <TH>User</TH>
                <TH>Organisation</TH>
                <TH>Plan</TH>
                <TH>Security</TH>
                <TH>Status</TH>
                <TH>Last login</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {users.data.users.map((user) => (
                <TR key={user.id} onClick={() => open(user)}>
                  <TD>
                    <div className="min-w-0">
                      <p className="truncate text-xs text-paper">{user.full_name}</p>
                      <p className="truncate text-2xs text-paper-faint">{user.email}</p>
                    </div>
                  </TD>
                  <TD>{user.org_name ?? "—"}</TD>
                  <TD>
                    <div className="flex items-center gap-1.5">
                      <Badge tone="outline">{titleCase(user.plan_code)}</Badge>
                      {user.subscription_status ? <StatusBadge status={user.subscription_status} /> : null}
                    </div>
                  </TD>
                  <TD>
                    <div className="flex gap-1.5">
                      <Badge tone={user.email_verified ? "gain" : "warn"}>{user.email_verified ? "verified" : "unverified"}</Badge>
                      <Badge tone={user.mfa_enabled ? "gain" : "neutral"}>{user.mfa_enabled ? "mfa" : "no mfa"}</Badge>
                    </div>
                  </TD>
                  <TD>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge status={user.status} />
                      {user.is_staff ? <Badge tone="gold">{user.staff_role ?? "staff"}</Badge> : null}
                    </div>
                  </TD>
                  <TD>{dateTime(user.last_login_at)}</TD>
                  <TD align="right">
                    <span className="text-2xs text-paper-faint">Manage</span>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState title="No users matched" description="Try a different search term." />
        )}
      </Panel>

      <Dialog
        open={Boolean(target)}
        onClose={() => setTarget(null)}
        title={target?.email ?? "User"}
        description="Changes are audited with your identity and the reason given."
        footer={
          <>
            <Button variant="ghost" onClick={() => setTarget(null)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={save}>
              Apply changes
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Account status" htmlFor="status">
            <Select id="status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="active">Active</option>
              <option value="pending">Pending</option>
              <option value="suspended">Suspended</option>
            </Select>
          </Field>
          <Field label="Staff role" htmlFor="role" hint="Only an owner can grant the owner role. Leave blank for a normal subscriber.">
            <Select id="role" value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="">No staff access</option>
              <option value="analyst">Analyst (read-only)</option>
              <option value="support">Support</option>
              <option value="admin">Admin</option>
              <option value="owner">Owner</option>
            </Select>
          </Field>
          <Field label="Reason" htmlFor="reason">
            <Textarea id="reason" value={reason} onChange={(event) => setReason(event.target.value)} className="min-h-16" />
          </Field>
          <p className="text-2xs leading-relaxed text-paper-faint">
            Suspending an account stops new orders at the organisation level. It does not silently liquidate positions.
          </p>
        </div>
      </Dialog>
    </div>
  );
}
