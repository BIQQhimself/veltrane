"use client";

import * as React from "react";
import { ExternalLink, Link2, RefreshCw, ShieldCheck } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { recordReferralClick, visitorId } from "@/lib/referral";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorNote, Skeleton } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";

type DerivAccount = {
  account_id: string;
  account_type?: string;
  currency?: string;
  balance?: number;
  is_virtual?: boolean;
};

export type DerivOAuthStatus = {
  configured: boolean;
  client_id: string;
  redirect_uri: string;
  scopes: string[];
  single_account_policy: boolean;
  referral: { url: string; enabled: boolean };
  connection: {
    id: string;
    status: string;
    account_id: string | null;
    account_type: string | null;
    currency: string | null;
    accounts: DerivAccount[];
    nickname: string;
    token: { kind: string; expires_at: string | null; expired: boolean; days_left?: number };
  } | null;
  note: string;
};

type StartResponse = { authorize_url: string; state: string; referral_url: string; scopes: string[] };

type ResultCopy = { tone: "success" | "info" | "error"; title: string; body: string };

const RESULT_COPY = {
  connected: {
    tone: "success",
    title: "Deriv connected",
    body: "Read-only sync is live. Trading stays off until you authorise it explicitly.",
  },
  denied: { tone: "info", title: "Authorisation cancelled", body: "Deriv reported that you cancelled. Nothing changed." },
  invalid: { tone: "error", title: "Authorisation incomplete", body: "Deriv returned no code. Start again when ready." },
  error: {
    tone: "error",
    title: "Deriv rejected the authorisation",
    body: "The link may have expired. Start again from this panel.",
  },
} satisfies Record<string, ResultCopy>;

function resultCopy(key: string): ResultCopy {
  return (RESULT_COPY as Record<string, ResultCopy | undefined>)[key] ?? RESULT_COPY.error;
}

export function DerivOAuthPanel({ onConnected }: { onConnected?: () => void }) {
  const toast = useToast();
  const status = useApi<DerivOAuthStatus>((signal) => api("/deriv/oauth/status", { signal }));
  const [busy, setBusy] = React.useState(false);
  const [switching, setSwitching] = React.useState<string | null>(null);
  const handled = React.useRef(false);

  // The callback lands here with ?deriv=connected|denied|error|invalid.
  React.useEffect(() => {
    if (handled.current || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const result = params.get("deriv");
    if (!result) return;
    handled.current = true;
    const copy = resultCopy(result);
    if (copy.tone === "error") toast.error(copy.title, copy.body);
    else if (copy.tone === "info") toast.info(copy.title, copy.body);
    else toast.success(copy.title, copy.body);
    status.refetch();
    onConnected?.();
    params.delete("deriv");
    params.delete("accounts");
    params.delete("reason");
    const query = params.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startOAuth() {
    setBusy(true);
    try {
      const result = await api<StartResponse>("/deriv/oauth/start", {
        method: "POST",
        body: {
          purpose: status.data?.connection ? "reconnect" : "connect",
          connection_id: status.data?.connection?.id ?? "",
          visitor_id: visitorId(),
        },
      });
      window.location.assign(result.authorize_url);
    } catch (error) {
      toast.error("Could not start Deriv authorisation", errorMessage(error));
      setBusy(false);
    }
  }

  function openReferral() {
    const url = status.data?.referral.url;
    if (!url) {
      toast.info("No referral link configured", "An administrator can add the Deriv partner link in the command centre.");
      return;
    }
    void recordReferralClick("deriv-signup");
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async function switchAccount(accountId: string) {
    const connection = status.data?.connection;
    if (!connection) return;
    setSwitching(accountId);
    try {
      const result = await api<{ account_type: string; is_demo: boolean }>(
        `/deriv/connections/${connection.id}/account`,
        { method: "POST", body: { account_id: accountId } },
      );
      toast.success(
        result.is_demo ? "Switched to the demo account" : "Switched to the live account",
        "One VELTRANE connection follows one Deriv account. Live trading still needs authorisation.",
      );
      status.refetch();
    } catch (error) {
      toast.error("Account switch failed", errorMessage(error));
    } finally {
      setSwitching(null);
    }
  }

  const data = status.data;
  const connection = data?.connection ?? null;
  const accounts = connection?.accounts ?? [];

  return (
    <Panel>
      <PanelHeader
        title="Deriv authorisation"
        subtitle="Official OAuth 2.0 with PKCE. VELTRANE never sees your Deriv password and never asks for payment scope."
        action={
          connection ? (
            <Badge tone={connection.token.expired ? "warn" : "gain"}>
              {connection.token.expired ? "reconnect needed" : "authorised"}
            </Badge>
          ) : (
            <Badge tone="outline">not connected</Badge>
          )
        }
      />
      <PanelBody className="space-y-4">
        {status.loading ? <Skeleton className="h-16 w-full" /> : null}
        {status.error ? <ErrorNote message={status.error} onRetry={status.refetch} /> : null}

        {data ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-line-soft bg-ink-900 px-3 py-2.5">
                <p className="text-2xs uppercase tracking-label text-paper-faint">Scopes requested</p>
                <p className="mt-1 text-xs text-paper">{data.scopes.join(" · ") || "—"}</p>
                <p className="mt-1 text-2xs text-paper-faint">
                  Payment scope is never requested: it would allow withdrawal operations.
                </p>
              </div>
              <div className="rounded-lg border border-line-soft bg-ink-900 px-3 py-2.5">
                <p className="text-2xs uppercase tracking-label text-paper-faint">One account per profile</p>
                <p className="mt-1 text-xs text-paper">
                  {connection
                    ? `${accounts.length} Deriv account${accounts.length === 1 ? "" : "s"} visible · using ${
                        connection.account_id ?? "—"
                      }`
                    : "Deriv demo and live accounts share one authorisation."}
                </p>
                <p className="mt-1 text-2xs text-paper-faint">Switching account type never creates a second profile.</p>
              </div>
            </div>

            {connection?.token.expires_at ? (
              <p className="text-2xs text-paper-faint">
                Access token expires {new Date(connection.token.expires_at).toLocaleString()}
                {connection.token.expired
                  ? " — Deriv does not issue refresh tokens, so reconnect to keep syncing."
                  : typeof connection.token.days_left === "number"
                    ? ` (${connection.token.days_left} day${connection.token.days_left === 1 ? "" : "s"} left)`
                    : ""}
              </p>
            ) : null}

            {accounts.length > 1 ? (
              <div className="space-y-2">
                <p className="text-2xs uppercase tracking-label text-paper-faint">Deriv accounts on this authorisation</p>
                <ul className="divide-y divide-line-soft/70 rounded-lg border border-line-soft">
                  {accounts.map((account) => {
                    const active = account.account_id === connection?.account_id;
                    return (
                      <li key={account.account_id} className="flex items-center justify-between gap-3 px-3 py-2">
                        <div>
                          <p className="num text-xs text-paper">{account.account_id}</p>
                          <p className="text-2xs text-paper-faint">
                            {account.account_type ?? "unknown"} · {account.currency ?? "—"}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          {account.account_type?.toLowerCase() === "demo" ? (
                            <Badge tone="info">demo</Badge>
                          ) : (
                            <Badge tone="warn">real funds</Badge>
                          )}
                          <Button
                            size="sm"
                            variant={active ? "ghost" : "secondary"}
                            disabled={active || switching === account.account_id}
                            onClick={() => switchAccount(account.account_id)}
                          >
                            {active ? "in use" : "use"}
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={startOAuth} loading={busy} disabled={!data.configured}>
                <ShieldCheck className="h-3.5 w-3.5" />
                {connection ? "Reconnect with Deriv" : "Connect Deriv with OAuth"}
              </Button>
              <Button variant="secondary" onClick={openReferral}>
                <Link2 className="h-3.5 w-3.5" />
                No Deriv account? Open the referral link
                <ExternalLink className="h-3 w-3" />
              </Button>
              <Button variant="ghost" onClick={status.refetch}>
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh
              </Button>
            </div>

            {!data.configured ? (
              <p className="text-2xs leading-relaxed text-warn">
                OAuth is not configured on this deployment. An administrator must register a Deriv application and set
                VELTRANE_DERIV_OAUTH_CLIENT_ID and VELTRANE_DERIV_OAUTH_REDIRECT_URI. Manual token entry below still
                works.
              </p>
            ) : (
              <p className="text-2xs leading-relaxed text-paper-faint">{data.note}</p>
            )}
          </>
        ) : null}
      </PanelBody>
    </Panel>
  );
}
