"use client";

import * as React from "react";
import { KeyRound, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, titleCase } from "@/lib/format";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Field, Input, Select } from "@/components/ui/input";
import { DerivOAuthPanel } from "@/components/app/deriv-oauth-panel";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import type { Connection } from "@/lib/types";

type ProviderInfo = {
  key: string;
  name: string;
  kind: string;
  status: string;
  requires_passphrase?: boolean;
  requires_api_secret?: boolean;
  requires_app_id?: boolean;
  token_label?: string;
  supports_oauth?: boolean;
  auth_style?: string;
  asset_classes?: string[];
  notes?: string;
};

type Providers = { providers: ProviderInfo[]; notice: string };
type Connections = { connections: Connection[]; limit: number | null; used: number };

export default function AccountsPage() {
  const toast = useToast();
  const { entitlements } = useAuth();
  const providers = useApi<Providers>((signal) => api("/connections/providers", { signal }));
  const connections = useApi<Connections>((signal) => api("/connections", { signal }));

  const [open, setOpen] = React.useState(false);
  const [provider, setProvider] = React.useState("paper");
  const [label, setLabel] = React.useState("My paper account");
  const [environment, setEnvironment] = React.useState("read_only");
  const [apiKey, setApiKey] = React.useState("");
  const [apiSecret, setApiSecret] = React.useState("");
  const [passphrase, setPassphrase] = React.useState("");
  const [appId, setAppId] = React.useState("");
  const [accountId, setAccountId] = React.useState("");
  const [attestation, setAttestation] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const selectedProvider = providers.data?.providers.find((item) => item.key === provider);
  const needsKeys = provider !== "paper";
  const needsSecret = needsKeys && (selectedProvider?.requires_api_secret ?? true);
  const needsPassphrase = Boolean(selectedProvider?.requires_passphrase);
  const needsAppId = Boolean(selectedProvider?.requires_app_id);
  const tokenLabel = selectedProvider?.token_label ?? "API key";
  const isDeriv = provider === "deriv";
  const rows = connections.data?.connections ?? [];

  async function createConnection(event?: React.FormEvent) {
    event?.preventDefault();
    setBusy(true);
    try {
      await api("/connections", {
        method: "POST",
        body: {
          provider,
          label,
          environment,
          api_key: apiKey,
          api_secret: apiSecret,
          passphrase,
          app_id: appId,
          account_id: accountId,
          withdrawal_attestation: attestation,
        },
      });
      toast.success(
        "Account connected",
        isDeriv
          ? "Deriv verified the token. Demo accounts can trade immediately; real accounts still need authorisation."
          : "Credentials are encrypted at rest. Sync to pull balances.",
      );
      setOpen(false);
      setApiKey("");
      setApiSecret("");
      setPassphrase("");
      setAppId("");
      setAccountId("");
      connections.refetch();
    } catch (error) {
      toast.error("Connection failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function sync(connection: Connection) {
    setBusy(true);
    try {
      const result = await api<{ balances?: number; positions?: number }>(
        `/connections/${connection.id}/sync`,
        { method: "POST" },
      );
      toast.success("Sync complete", `${result.balances ?? 0} balances, ${result.positions ?? 0} positions updated.`);
      connections.refetch();
    } catch (error) {
      toast.error("Sync failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(connection: Connection) {
    if (!window.confirm(`Revoke ${connection.label}? Stored credentials are destroyed and no further syncs occur.`)) {
      return;
    }
    setBusy(true);
    try {
      await api(`/connections/${connection.id}`, { method: "DELETE" });
      toast.info("Connection revoked");
      connections.refetch();
    } catch (error) {
      toast.error("Revoke failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Integrations"
        title="Connected accounts"
        description="VELTRANE reads balances and positions from venues you already use. It never holds funds and never asks for withdrawal permission."
        action={
          <Button size="sm" onClick={() => setOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            Connect account
          </Button>
        }
      />

      {connections.error ? <ErrorNote message={connections.error} onRetry={connections.refetch} /> : null}

      <DerivOAuthPanel onConnected={() => connections.refetch()} />

      <Panel>
        <PanelHeader
          title="Your connections"
          subtitle={
            connections.data ? `${connections.data.used} of ${connections.data.limit ?? "unlimited"} used` : undefined
          }
          action={
            <Badge tone="gold">
              limit {entitlements?.limits?.max_connections ?? connections.data?.limit ?? "—"}
            </Badge>
          }
        />
        {connections.loading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : rows.length ? (
          <ul className="divide-y divide-line-soft/70">
            {rows.map((connection) => (
              <li key={connection.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm text-paper">{connection.label}</p>
                    <StatusBadge status={connection.status} />
                    <Badge tone="outline">{titleCase(connection.provider)}</Badge>
                    {connection.provider_account_type?.toLowerCase() === "demo" ? (
                      <Badge tone="info">demo account</Badge>
                    ) : (
                      <Badge tone={connection.environment === "read_only" ? "neutral" : "warn"}>
                        {titleCase(connection.environment)}
                      </Badge>
                    )}
                    {connection.is_sandbox ? <Badge tone="info">sandbox</Badge> : null}
                  </div>
                  <p className="mt-1 text-2xs text-paper-faint">
                    Last sync {dateTime(connection.last_sync_at)}
                    {connection.last_error ? <span className="text-loss"> · {connection.last_error}</span> : null}
                  </p>
                  {connection.provider === "deriv" ? (
                    <p className="mt-1 flex flex-wrap items-center gap-1.5 text-2xs text-paper-faint">
                      <span className="num">{connection.provider_account_id ?? "account pending"}</span>
                      {connection.provider_currency ? <span>· {connection.provider_currency}</span> : null}
                      {connection.provider_account_type ? (
                        <Badge
                          tone={connection.provider_account_type.toLowerCase() === "demo" ? "info" : "warn"}
                        >
                          {connection.provider_account_type.toLowerCase() === "demo" ? "demo" : "real funds"}
                        </Badge>
                      ) : null}
                      {connection.provider_meta?.nickname ? (
                        <span>· {connection.provider_meta.nickname}</span>
                      ) : null}
                      {connection.last_auth_error ? (
                        <span className="text-loss">· {connection.last_auth_error}</span>
                      ) : null}
                    </p>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => sync(connection)}
                    disabled={busy || connection.status === "revoked"}
                  >
                    <RefreshCw className="h-3 w-3" />
                    Sync
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => revoke(connection)}
                    disabled={busy || connection.status === "revoked"}
                    aria-label={`Revoke ${connection.label}`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="No accounts connected"
            description="Start with the simulation venue: it needs no keys and lets you complete onboarding immediately."
            action={
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setProvider("paper");
                  setEnvironment("paper");
                  setOpen(true);
                }}
              >
                Connect the simulation venue
              </Button>
            }
          />
        )}
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel>
          <PanelHeader title="Credential handling" />
          <PanelBody className="space-y-3">
            {[
              ["Encrypted at rest", "Envelope encryption with a wrapped data key per connection."],
              ["Trading-only keys", "You disable withdrawal permission on the venue itself."],
              ["Never returned", "No endpoint returns a secret. Only a masked hint and a fingerprint."],
              ["Revocable", "Revoking destroys the stored ciphertext immediately."],
            ].map(([title, body]) => (
              <div key={title} className="flex items-start gap-2.5">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gain/80" aria-hidden />
                <div>
                  <p className="text-xs text-paper">{title}</p>
                  <p className="mt-0.5 text-2xs text-paper-faint">{body}</p>
                </div>
              </div>
            ))}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Provider status" subtitle="Literal, not aspirational" />
          <PanelBody className="space-y-2">
            {(providers.data?.providers ?? []).map((item) => (
              <div
                key={item.key}
                className="flex items-center justify-between gap-3 border-b border-line-soft/60 py-2 last:border-0"
              >
                <div>
                  <p className="text-xs text-paper">{item.name}</p>
                  <p className="text-2xs text-paper-faint">{item.notes ?? item.kind}</p>
                </div>
                <Badge
                  tone={
                    item.status === "verified_trading"
                      ? "gain"
                      : item.status === "verified_read_only" || item.status === "simulated"
                        ? "info"
                        : "warn"
                  }
                >
                  {item.status.replace(/_/g, " ")}
                </Badge>
              </div>
            ))}
            {providers.data ? (
              <p className="pt-2 text-2xs leading-relaxed text-paper-faint">{providers.data.notice}</p>
            ) : null}
          </PanelBody>
        </Panel>
      </div>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Connect an account"
        description="Read-only is the default. Trading permission on a connection is separate from live-trading authorisation."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={() => createConnection()} disabled={needsKeys && !attestation}>
              Connect
            </Button>
          </>
        }
      >
        <form onSubmit={createConnection} className="space-y-3">
          <Field label="Provider" htmlFor="provider">
            <Select
              id="provider"
              value={provider}
              onChange={(event) => {
                const next = event.target.value;
                setProvider(next);
                if (next === "paper") setEnvironment("paper");
                else if (environment === "paper") setEnvironment("read_only");
              }}
            >
              {(providers.data?.providers ?? []).map((item) => (
                <option key={item.key} value={item.key}>
                  {item.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Label" htmlFor="label" hint="How this account appears in your workspace.">
            <Input id="label" value={label} onChange={(event) => setLabel(event.target.value)} required minLength={2} />
          </Field>
          <Field
            label="Permission"
            htmlFor="environment"
            hint={provider === "paper" ? "The simulation venue executes locally; it has no live mode." : undefined}
          >
            {provider === "paper" ? (
              <Select id="environment" value="paper" disabled>
                <option value="paper">Paper (simulation only)</option>
              </Select>
            ) : (
              <Select id="environment" value={environment} onChange={(event) => setEnvironment(event.target.value)}>
                <option value="read_only">Read-only</option>
                <option value="paper">Paper</option>
                <option value="live">Live (requires authorisation)</option>
              </Select>
            )}
          </Field>

          {needsKeys ? (
            <>
              <Field
                label={tokenLabel}
                htmlFor="api_key"
                hint={
                  isDeriv
                    ? "Deriv → Settings → API token. Grant read and trade scopes. Never grant withdrawal."
                    : "Create a key with read and trade permissions only. Never enable withdrawals."
                }
              >
                <Input
                  id="api_key"
                  type={isDeriv ? "password" : "text"}
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  required
                />
              </Field>
              {needsSecret ? (
                <Field label="API secret" htmlFor="api_secret">
                  <Input
                    id="api_secret"
                    type="password"
                    value={apiSecret}
                    onChange={(event) => setApiSecret(event.target.value)}
                    autoComplete="new-password"
                    required
                  />
                </Field>
              ) : null}
              {needsAppId ? (
                <Field
                  label="App ID"
                  htmlFor="app_id"
                  hint="The Deriv application id this token was issued for. Stored with the connection, never returned."
                >
                  <Input
                    id="app_id"
                    value={appId}
                    onChange={(event) => setAppId(event.target.value)}
                    autoComplete="off"
                    inputMode="numeric"
                  />
                </Field>
              ) : null}
              {isDeriv ? (
                <Field
                  label="Account ID (optional)"
                  htmlFor="account_id"
                  hint="Leave blank to use the token's default account. Demo accounts start with VRTC."
                >
                  <Input
                    id="account_id"
                    value={accountId}
                    onChange={(event) => setAccountId(event.target.value)}
                    autoComplete="off"
                  />
                </Field>
              ) : null}
              {needsPassphrase ? (
                <Field label="Passphrase" htmlFor="passphrase">
                  <Input
                    id="passphrase"
                    type="password"
                    value={passphrase}
                    onChange={(event) => setPassphrase(event.target.value)}
                    autoComplete="new-password"
                  />
                </Field>
              ) : null}
              <label className="flex items-start gap-2.5 rounded-lg border border-line-soft bg-ink-900 px-3 py-2.5 text-2xs leading-relaxed text-paper-muted">
                <input
                  type="checkbox"
                  checked={attestation}
                  onChange={(event) => setAttestation(event.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-champagne-500"
                />
                I confirm this key has no withdrawal permission and belongs to an account I control.
              </label>
            </>
          ) : (
            <div className="rounded-lg border border-info/25 bg-info/5 px-3 py-2.5">
              <p className="flex items-center gap-2 text-xs text-info">
                <KeyRound className="h-3.5 w-3.5" aria-hidden />
                No credentials required
              </p>
              <p className="mt-1 text-2xs text-paper-faint">
                The simulation venue is internal. Balances are simulated and excluded from live equity.
              </p>
            </div>
          )}
        </form>
      </Dialog>
    </div>
  );
}
