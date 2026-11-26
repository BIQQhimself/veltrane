"use client";

import * as React from "react";
import { AlertTriangle, Power } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNote, Skeleton } from "@/components/ui/data";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";

type Policy = { policy: { id: string | null; version: number; rules: Record<string, number | boolean>; defaults: Record<string, number | boolean> } };
type Switch = { id: string; scope: string; target: string; engaged: boolean; reason: string | null; engaged_at: string | null; released_at: string | null };
type Flags = { flags: Array<{ key: string; enabled: boolean; description: string; rollout: Record<string, unknown>; updated_at: string }> };
type LiveSwitch = {
  deployment_enabled: boolean;
  staff_enabled: boolean;
  effective: boolean;
  reason: string;
  updated_at: string | null;
  updated_by: string | null;
  note: string;
};

export default function AdminRiskPage() {
  const toast = useToast();
  const policy = useApi<Policy>((signal) => api("/admin/risk/policy", { signal }));
  const switches = useApi<{ switches: Switch[]; platform_live_enabled: boolean }>((signal) => api("/admin/kill-switches", { signal }));
  const flags = useApi<Flags>((signal) => api("/admin/feature-flags", { signal }));
  const liveSwitch = useApi<LiveSwitch>((signal) => api("/admin/live-trading", { signal }));

  const [rules, setRules] = React.useState<Record<string, number | boolean>>({});
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [confirmHalt, setConfirmHalt] = React.useState(false);
  const [liveDialog, setLiveDialog] = React.useState<"enable" | "disable" | null>(null);
  const [liveReason, setLiveReason] = React.useState("");
  const [liveConfirm, setLiveConfirm] = React.useState("");
  const [haltReason, setHaltReason] = React.useState("Operator halt: reviewing risk controls");

  React.useEffect(() => {
    if (policy.data) setRules(policy.data.policy.rules);
  }, [policy.data]);

  const globalSwitch = switches.data?.switches.find((item) => item.scope === "global" && item.engaged);

  async function savePolicy() {
    setBusy(true);
    try {
      await api("/admin/risk/policy", { method: "PUT", body: { rules, reason } });
      toast.success("Risk policy updated", "A new version was created and audited.");
      setReason("");
      policy.refetch();
    } catch (error) {
      toast.error("Policy update failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function toggleFlag(key: string, enabled: boolean) {
    setBusy(true);
    try {
      await api(`/admin/feature-flags/${key}`, { method: "PUT", body: { enabled } });
      toast.info(`${key} ${enabled ? "enabled" : "disabled"}`);
      flags.refetch();
    } catch (error) {
      toast.error("Flag update failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function setLiveTrading(enabled: boolean) {
    setBusy(true);
    try {
      await api("/admin/live-trading", {
        method: "PUT",
        body: { enabled, reason: liveReason, confirm: liveConfirm },
      });
      toast.info(
        enabled ? "Live trading armed" : "Live trading halted",
        enabled
          ? "Every order still passes the risk engine and each user's own authorisation."
          : "New live orders are refused platform-wide until both keys allow them.",
      );
      setLiveDialog(null);
      setLiveConfirm("");
      setLiveReason("");
      liveSwitch.refetch();
      switches.refetch();
    } catch (error) {
      toast.error("Live trading switch failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function engageGlobal() {
    setBusy(true);
    try {
      await api("/admin/kill-switches/engage", { method: "POST", body: { reason: haltReason } });
      toast.error("Global trading halted", "Every order is refused until released.");
      setConfirmHalt(false);
      switches.refetch();
    } catch (error) {
      toast.error("Halt failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function releaseGlobal() {
    setBusy(true);
    try {
      await api("/admin/kill-switches/release", { method: "POST", body: { reason: haltReason } });
      toast.success("Global halt released");
      switches.refetch();
    } catch (error) {
      toast.error("Release failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Controls"
        title="Risk & feature flags"
        description="The deterministic rules every order is measured against. Changes create a new policy version; nothing is edited in place."
        action={
          <Badge tone={globalSwitch ? "loss" : "gain"}>{globalSwitch ? "global halt engaged" : "trading permitted"}</Badge>
        }
      />

      {policy.error ? <ErrorNote message={policy.error} onRetry={policy.refetch} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel>
          <PanelHeader
            title="Global risk policy"
            subtitle={policy.data ? `version ${policy.data.policy.version}` : undefined}
            action={<Badge tone="gold">{Object.keys(rules).length} rules</Badge>}
          />
          <PanelBody className="space-y-4">
            {policy.loading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <>
                <div className="grid gap-2 sm:grid-cols-2">
                  {Object.entries(rules).map(([key, value]) =>
                    typeof value === "boolean" ? (
                      <label key={key} className="flex items-center justify-between rounded-lg border border-line-soft px-3 py-2 text-xs">
                        <span className="text-paper-muted">{key.replace(/_/g, " ")}</span>
                        <input
                          type="checkbox"
                          checked={value}
                          onChange={(event) => setRules((current) => ({ ...current, [key]: event.target.checked }))}
                          className="h-3.5 w-3.5 accent-champagne-500"
                        />
                      </label>
                    ) : (
                      <Field key={key} label={key.replace(/_/g, " ")} htmlFor={key}>
                        <Input
                          id={key}
                          type="number"
                          step="any"
                          value={String(value)}
                          onChange={(event) => setRules((current) => ({ ...current, [key]: Number(event.target.value) }))}
                        />
                      </Field>
                    ),
                  )}
                </div>
                <Field label="Reason for change" htmlFor="policy_reason" hint="Recorded in the audit log with your identity.">
                  <Textarea
                    id="policy_reason"
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    className="min-h-16"
                    minLength={3}
                  />
                </Field>
                <Button onClick={savePolicy} loading={busy} disabled={reason.trim().length < 3}>
                  Publish new policy version
                </Button>
              </>
            )}
          </PanelBody>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHeader
              title="Live trading master switch"
              subtitle="Two keys must agree: the operator flag and this staff key"
              action={
                <Badge tone={liveSwitch.data?.effective ? "loss" : "gain"}>
                  {liveSwitch.data?.effective ? "live armed" : "live off"}
                </Badge>
              }
            />
            <PanelBody className="space-y-3">
              {liveSwitch.loading ? (
                <Skeleton className="h-20 w-full" />
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2 text-2xs">
                    <div className="rounded-lg border border-line-soft px-3 py-2">
                      <p className="text-paper-faint">Operator key</p>
                      <p className="mt-1 text-paper">
                        {liveSwitch.data?.deployment_enabled ? "enabled" : "disabled"}
                      </p>
                    </div>
                    <div className="rounded-lg border border-line-soft px-3 py-2">
                      <p className="text-paper-faint">Staff key</p>
                      <p className="mt-1 text-paper">{liveSwitch.data?.staff_enabled ? "enabled" : "disabled"}</p>
                    </div>
                  </div>
                  <p className="text-2xs leading-relaxed text-paper-faint">
                    {liveSwitch.data?.note ?? ""}
                    {liveSwitch.data?.updated_by
                      ? ` Last changed by ${liveSwitch.data.updated_by} at ${dateTime(liveSwitch.data.updated_at)}.`
                      : ""}
                  </p>
                  {liveSwitch.data?.staff_enabled ? (
                    <Button variant="danger" onClick={() => setLiveDialog("disable")} disabled={busy}>
                      <Power className="h-3.5 w-3.5" />
                      Disable live trading
                    </Button>
                  ) : (
                    <Button
                      variant="secondary"
                      onClick={() => setLiveDialog("enable")}
                      disabled={busy || !liveSwitch.data?.deployment_enabled}
                    >
                      <Power className="h-3.5 w-3.5" />
                      Enable live trading
                    </Button>
                  )}
                </>
              )}
            </PanelBody>
          </Panel>

          <Panel className={globalSwitch ? "border-loss/40" : undefined}>
            <PanelHeader title="Global kill switch" subtitle="Durable and independent of the app" />
            <PanelBody className="space-y-3">
              <div className="flex items-start gap-2 text-2xs leading-relaxed text-paper-faint">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" aria-hidden />
                Halting stops new orders at every venue. It does not close positions automatically; do that
                deliberately.
              </div>
              <Field label="Reason" htmlFor="halt_reason">
                <Textarea id="halt_reason" value={haltReason} onChange={(event) => setHaltReason(event.target.value)} className="min-h-14" />
              </Field>
              {globalSwitch ? (
                <Button variant="success" onClick={releaseGlobal} loading={busy}>
                  <Power className="h-3.5 w-3.5" />
                  Release global halt
                </Button>
              ) : (
                <Button variant="danger" onClick={() => setConfirmHalt(true)} disabled={busy}>
                  <Power className="h-3.5 w-3.5" />
                  Engage global halt
                </Button>
              )}
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader title="Recent switches" subtitle="Most recent first" />
            {switches.loading ? (
              <div className="p-5">
                <Skeleton className="h-20 w-full" />
              </div>
            ) : switches.data && switches.data.switches.length ? (
              <Table>
                <THead>
                  <TR>
                    <TH>Scope</TH>
                    <TH>Target</TH>
                    <TH>State</TH>
                    <TH>At</TH>
                  </TR>
                </THead>
                <TBody>
                  {switches.data.switches.slice(0, 8).map((item) => (
                    <TR key={item.id}>
                      <TD>{item.scope}</TD>
                      <TD mono>{item.target.slice(0, 12)}</TD>
                      <TD>
                        <Badge tone={item.engaged ? "loss" : "neutral"}>{item.engaged ? "engaged" : "released"}</Badge>
                      </TD>
                      <TD>{dateTime(item.engaged_at ?? item.released_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : (
              <p className="px-5 py-6 text-xs text-paper-faint">No switches have been used.</p>
            )}
          </Panel>
        </div>
      </div>

      <Panel>
        <PanelHeader title="Feature flags" subtitle="Rollout controls, audited per change" />
        <PanelBody className="space-y-2">
          {flags.loading ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            (flags.data?.flags ?? []).map((flag) => (
              <div key={flag.key} className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft/60 py-2 last:border-0">
                <div className="min-w-0">
                  <p className="num text-xs text-paper">{flag.key}</p>
                  <p className="text-2xs text-paper-faint">{flag.description || "No description"}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xs text-paper-faint">{dateTime(flag.updated_at)}</span>
                  <Button
                    size="sm"
                    variant={flag.enabled ? "secondary" : "ghost"}
                    onClick={() => toggleFlag(flag.key, !flag.enabled)}
                    disabled={busy}
                  >
                    {flag.enabled ? "Enabled" : "Disabled"}
                  </Button>
                </div>
              </div>
            ))
          )}
        </PanelBody>
      </Panel>

      <Dialog
        open={liveDialog !== null}
        onClose={() => setLiveDialog(null)}
        title={liveDialog === "enable" ? "Enable live trading" : "Disable live trading"}
        description="Live execution also needs the operator flag, each user's own authorisation and every risk check. This change is audit logged."
        footer={
          <>
            <Button variant="ghost" onClick={() => setLiveDialog(null)}>
              Cancel
            </Button>
            <Button
              variant={liveDialog === "enable" ? "danger" : "secondary"}
              loading={busy}
              disabled={
                liveReason.trim().length < 3 ||
                liveConfirm.trim().toUpperCase() !==
                  (liveDialog === "enable" ? "ENABLE LIVE TRADING" : "DISABLE LIVE TRADING")
              }
              onClick={() => setLiveTrading(liveDialog === "enable")}
            >
              {liveDialog === "enable" ? "Enable" : "Disable"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Reason" htmlFor="live_reason" hint="Recorded with your identity.">
            <Textarea
              id="live_reason"
              value={liveReason}
              onChange={(event) => setLiveReason(event.target.value)}
              className="min-h-14"
            />
          </Field>
          <Field
            label="Confirmation"
            htmlFor="live_confirm"
            hint={`Type ${liveDialog === "enable" ? "ENABLE LIVE TRADING" : "DISABLE LIVE TRADING"} to continue.`}
          >
            <Input
              id="live_confirm"
              value={liveConfirm}
              onChange={(event) => setLiveConfirm(event.target.value)}
              autoComplete="off"
            />
          </Field>
        </div>
      </Dialog>

      <Dialog
        open={confirmHalt}
        onClose={() => setConfirmHalt(false)}
        title="Engage the global kill switch"
        description="This refuses every new order on the platform until released. It is recorded with your identity."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmHalt(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={busy} onClick={engageGlobal}>
              Halt all trading
            </Button>
          </>
        }
      >
        <p className="text-xs leading-relaxed text-paper-muted">{haltReason}</p>
      </Dialog>
    </div>
  );
}
