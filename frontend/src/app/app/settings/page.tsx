"use client";

import * as React from "react";
import { AlertTriangle, KeyRound, ShieldCheck } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, titleCase } from "@/lib/format";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KeyValue, Skeleton } from "@/components/ui/data";
import { Tabs } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";

type LiveState = {
  platform_live_enabled: boolean;
  entitlement: boolean;
  status: string;
  live_enabled: boolean;
  checklist: Record<string, boolean>;
  checklist_items: Record<string, string>;
  risk_document_version: string;
  authorized_at: string | null;
  confirm_expires_at: string | null;
  jurisdiction: string | null;
  note: string;
};

type StartResponse = { status: string; confirmation_token: string; cooloff_seconds: number; warning: string };

const MARKETS = ["crypto", "forex", "indices"];

export default function SettingsPage() {
  const toast = useToast();
  const { user, organization, refresh, logout } = useAuth();
  const tradingState = useApi<{ live: LiveState }>((signal) => api("/trading/state", { signal }));
  const live = { data: tradingState.data?.live ?? null, loading: tradingState.loading, refetch: tradingState.refetch };
  const [tab, setTab] = React.useState("profile");

  const [fullName, setFullName] = React.useState(user?.full_name ?? "");
  const [timezone, setTimezone] = React.useState(String(user?.preferences?.timezone ?? "UTC"));
  const [country, setCountry] = React.useState(String(user?.preferences?.country ?? "GB"));
  const [marketing, setMarketing] = React.useState(Boolean(user?.preferences?.marketing_opt_in));

  const [experience, setExperience] = React.useState("beginner");
  const [appetite, setAppetite] = React.useState("balanced");
  const [maxDrawdown, setMaxDrawdown] = React.useState("10");
  const [maxPosition, setMaxPosition] = React.useState("5");
  const [horizon, setHorizon] = React.useState("swing");
  const [markets, setMarkets] = React.useState<string[]>(["crypto"]);

  const [mfaUri, setMfaUri] = React.useState<string | null>(null);
  const [mfaSecret, setMfaSecret] = React.useState<string | null>(null);
  const [mfaCode, setMfaCode] = React.useState("");
  const [recoveryCodes, setRecoveryCodes] = React.useState<string[] | null>(null);
  const [disablePassword, setDisablePassword] = React.useState("");

  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");

  const [checklist, setChecklist] = React.useState<Record<string, boolean>>({});
  const [acknowledged, setAcknowledged] = React.useState(false);
  const [jurisdiction, setJurisdiction] = React.useState(String(user?.preferences?.country ?? "GB"));
  const [totp, setTotp] = React.useState("");
  const [confirmationToken, setConfirmationToken] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (user) {
      setFullName(user.full_name ?? "");
      setTimezone(String(user.preferences?.timezone ?? "UTC"));
      setCountry(String(user.preferences?.country ?? "GB"));
      setMarketing(Boolean(user.preferences?.marketing_opt_in));
      setJurisdiction(String(user.preferences?.country ?? "GB"));
    }
  }, [user]);

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/users/me", { method: "PATCH", body: { full_name: fullName, timezone, country, marketing_opt_in: marketing } });
      await refresh();
      toast.success("Profile saved");
    } catch (error) {
      toast.error("Could not save profile", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveRiskProfile(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/users/me/risk-profile", {
        method: "PUT",
        body: {
          experience,
          risk_appetite: appetite,
          max_drawdown_pct: Number(maxDrawdown),
          max_position_pct: Number(maxPosition),
          preferred_markets: markets,
          horizon,
        },
      });
      await refresh();
      toast.success("Risk preferences saved", "These inform defaults; the risk engine enforces the hard limits.");
    } catch (error) {
      toast.error("Could not save preferences", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function beginMfa() {
    setBusy(true);
    try {
      const result = await api<{ otpauth_uri?: string; secret?: string; provisioning_uri?: string }>("/auth/mfa/setup", { method: "POST" });
      setMfaUri(result.otpauth_uri ?? result.provisioning_uri ?? null);
      setMfaSecret(result.secret ?? null);
    } catch (error) {
      toast.error("Could not start MFA setup", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function enableMfa() {
    setBusy(true);
    try {
      const result = await api<{ recovery_codes: string[] }>("/auth/mfa/enable", { method: "POST", body: { code: mfaCode.trim() } });
      setRecoveryCodes(result.recovery_codes);
      setMfaCode("");
      setMfaUri(null);
      await refresh();
      toast.success("Two-factor enabled", "Store the recovery codes offline.");
    } catch (error) {
      toast.error("Could not enable MFA", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function disableMfa() {
    setBusy(true);
    try {
      await api("/auth/mfa/disable", { method: "POST", body: { password: disablePassword } });
      setDisablePassword("");
      await refresh();
      toast.info("Two-factor disabled", "We recommend keeping it on for any account that can trade.");
    } catch (error) {
      toast.error("Could not disable MFA", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: { current_password: currentPassword, new_password: newPassword },
      });
      setCurrentPassword("");
      setNewPassword("");
      toast.success("Password changed", "Other sessions were invalidated.");
    } catch (error) {
      toast.error("Could not change password", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function startLiveAuthorization() {
    setBusy(true);
    try {
      const result = await api<StartResponse>("/trading/live-authorization/start", {
        method: "POST",
        body: {
          acknowledged,
          checklist,
          totp_code: totp || null,
          jurisdiction: jurisdiction.toUpperCase(),
        },
      });
      setConfirmationToken(result.confirmation_token);
      setTotp("");
      toast.info("Authorisation started", `Confirm after ${Math.round(result.cooloff_seconds / 60)} minutes.`);
      live.refetch();
    } catch (error) {
      toast.error("Authorisation could not start", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function confirmLiveAuthorization() {
    if (!confirmationToken) return;
    setBusy(true);
    try {
      await api("/trading/live-authorization/confirm", {
        method: "POST",
        body: { confirmation_token: confirmationToken },
      });
      setConfirmationToken(null);
      toast.success("Live authorisation recorded", "Orders still require the platform gate and a passing risk check.");
      live.refetch();
      await refresh();
    } catch (error) {
      toast.error("Confirmation failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function revokeLiveAuthorization() {
    setBusy(true);
    try {
      await api("/trading/live-authorization/revoke", {
        method: "POST",
        body: { reason: "Revoked by account owner in settings" },
      });
      toast.info("Live authorisation revoked");
      live.refetch();
      await refresh();
    } catch (error) {
      toast.error("Revoke failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Account"
        title="Settings"
        description="Security, risk preferences and the live-trading authorisation. Every change here is audited."
        action={<Badge tone="gold">{titleCase(user?.staff_role ?? "member")}</Badge>}
      />

      <Tabs
        tabs={[
          { id: "profile", label: "Profile" },
          { id: "security", label: "Security" },
          { id: "risk", label: "Risk preferences" },
          { id: "live", label: "Live authorisation" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "profile" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <PanelHeader title="Profile" />
            <PanelBody>
              <form onSubmit={saveProfile} className="space-y-3">
                <Field label="Full name" htmlFor="full_name">
                  <Input id="full_name" value={fullName} onChange={(event) => setFullName(event.target.value)} minLength={2} />
                </Field>
                <Field label="Email" htmlFor="email" hint="Contact support to change the address on your account.">
                  <Input id="email" value={user?.email ?? ""} disabled />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Timezone" htmlFor="timezone">
                    <Input id="timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)} />
                  </Field>
                  <Field label="Country" htmlFor="country">
                    <Input id="country" value={country} maxLength={2} onChange={(event) => setCountry(event.target.value)} />
                  </Field>
                </div>
                <label className="flex items-center gap-2 text-xs text-paper-muted">
                  <input
                    type="checkbox"
                    checked={marketing}
                    onChange={(event) => setMarketing(event.target.checked)}
                    className="h-3.5 w-3.5 accent-champagne-500"
                  />
                  Send me product updates (never trade signals or performance claims)
                </label>
                <Button type="submit" loading={busy}>
                  Save profile
                </Button>
              </form>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader title="Account" />
            <PanelBody>
              <KeyValue
                items={[
                  { label: "User ID", value: <span className="num text-2xs">{user?.id}</span> },
                  { label: "Organisation", value: organization?.name ?? "—" },
                  { label: "Email verified", value: user?.email_verified ? "Yes" : "No" },
                  { label: "Two-factor", value: user?.mfa_enabled ? <Badge tone="gain">enabled</Badge> : <Badge tone="warn">off</Badge> },
                  { label: "Role", value: titleCase(user?.staff_role ?? "owner") },
                  { label: "Onboarding", value: `${user?.onboarding_step ?? 0} / 10` },
                ]}
              />
              <Button
                variant="ghost"
                size="sm"
                className="mt-4"
                onClick={async () => {
                  try {
                    await api("/auth/logout-all", { method: "POST" });
                  } finally {
                    await logout();
                  }
                }}
              >
                Sign out everywhere
              </Button>
            </PanelBody>
          </Panel>
        </div>
      ) : null}

      {tab === "security" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <PanelHeader title="Two-factor authentication" subtitle="Required before live authorisation if enabled" />
            <PanelBody className="space-y-3">
              {user?.mfa_enabled ? (
                <>
                  <div className="flex items-center gap-2 text-xs text-gain">
                    <ShieldCheck className="h-4 w-4" aria-hidden /> Enabled on this account
                  </div>
                  <Field label="Confirm password to disable" htmlFor="disable_password">
                    <Input
                      id="disable_password"
                      type="password"
                      value={disablePassword}
                      onChange={(event) => setDisablePassword(event.target.value)}
                    />
                  </Field>
                  <Button variant="ghost" size="sm" onClick={disableMfa} disabled={busy || !disablePassword}>
                    Disable two-factor
                  </Button>
                </>
              ) : mfaUri ? (
                <>
                  <p className="text-xs text-paper-muted">
                    Add this secret to your authenticator app, then enter the six-digit code.
                  </p>
                  <div className="rounded-lg border border-line-soft bg-ink-900 p-3">
                    <p className="label">Secret</p>
                    <p className="num mt-1 break-all text-xs text-paper">{mfaSecret}</p>
                    <p className="mt-2 break-all text-2xs text-paper-faint">{mfaUri}</p>
                  </div>
                  <Field label="Code" htmlFor="mfa_code">
                    <Input
                      id="mfa_code"
                      inputMode="numeric"
                      value={mfaCode}
                      onChange={(event) => setMfaCode(event.target.value)}
                      maxLength={8}
                    />
                  </Field>
                  <Button onClick={enableMfa} loading={busy} disabled={mfaCode.length < 6}>
                    Enable
                  </Button>
                </>
              ) : (
                <>
                  <p className="text-xs leading-relaxed text-paper-muted">
                    A second factor protects the account that can authorise real-money execution.
                  </p>
                  <Button variant="secondary" onClick={beginMfa} loading={busy}>
                    <KeyRound className="h-3.5 w-3.5" />
                    Begin setup
                  </Button>
                </>
              )}

              {recoveryCodes ? (
                <div className="rounded-lg border border-warn/30 bg-warn/5 p-3">
                  <p className="text-2xs uppercase tracking-label text-warn">Recovery codes — shown once</p>
                  <div className="mt-2 grid grid-cols-2 gap-1">
                    {recoveryCodes.map((code) => (
                      <span key={code} className="num text-2xs text-paper">
                        {code}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader title="Password" subtitle="At least 12 characters" />
            <PanelBody>
              <form onSubmit={changePassword} className="space-y-3">
                <Field label="Current password" htmlFor="current_password">
                  <Input
                    id="current_password"
                    type="password"
                    autoComplete="current-password"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    required
                  />
                </Field>
                <Field label="New password" htmlFor="new_password">
                  <Input
                    id="new_password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    required
                  />
                </Field>
                <Button type="submit" loading={busy}>
                  Change password
                </Button>
              </form>
            </PanelBody>
          </Panel>
        </div>
      ) : null}

      {tab === "risk" ? (
        <Panel>
          <PanelHeader
            title="Risk preferences"
            subtitle="These shape defaults and warnings. The risk engine enforces hard limits regardless."
          />
          <PanelBody>
            <form onSubmit={saveRiskProfile} className="grid gap-4 sm:grid-cols-2">
              <Field label="Experience" htmlFor="experience">
                <Select id="experience" value={experience} onChange={(event) => setExperience(event.target.value)}>
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </Select>
              </Field>
              <Field label="Risk appetite" htmlFor="appetite">
                <Select id="appetite" value={appetite} onChange={(event) => setAppetite(event.target.value)}>
                  <option value="conservative">Conservative</option>
                  <option value="balanced">Balanced</option>
                  <option value="aggressive">Aggressive</option>
                </Select>
              </Field>
              <Field label="Maximum drawdown (%)" htmlFor="max_dd" hint="Between 1 and 50.">
                <Input
                  id="max_dd"
                  type="number"
                  min="1"
                  max="50"
                  value={maxDrawdown}
                  onChange={(event) => setMaxDrawdown(event.target.value)}
                />
              </Field>
              <Field label="Maximum position (% of equity)" htmlFor="max_pos" hint="Between 0.5 and 25.">
                <Input
                  id="max_pos"
                  type="number"
                  min="0.5"
                  max="25"
                  step="0.5"
                  value={maxPosition}
                  onChange={(event) => setMaxPosition(event.target.value)}
                />
              </Field>
              <Field label="Horizon" htmlFor="horizon">
                <Select id="horizon" value={horizon} onChange={(event) => setHorizon(event.target.value)}>
                  <option value="scalping">Scalping</option>
                  <option value="day">Day trading</option>
                  <option value="swing">Swing</option>
                  <option value="position">Position</option>
                </Select>
              </Field>
              <Field label="Preferred markets" htmlFor="markets">
                <div className="flex flex-wrap gap-3 pt-1">
                  {MARKETS.map((market) => (
                    <label key={market} className="flex items-center gap-1.5 text-xs text-paper-muted">
                      <input
                        type="checkbox"
                        checked={markets.includes(market)}
                        onChange={(event) =>
                          setMarkets((current) =>
                            event.target.checked ? [...current, market] : current.filter((item) => item !== market),
                          )
                        }
                        className="h-3.5 w-3.5 accent-champagne-500"
                      />
                      {titleCase(market)}
                    </label>
                  ))}
                </div>
              </Field>
              <div className="sm:col-span-2">
                <Button type="submit" loading={busy}>
                  Save preferences
                </Button>
              </div>
            </form>
          </PanelBody>
        </Panel>
      ) : null}

      {tab === "live" ? (
        <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
          <Panel>
            <PanelHeader
              title="Live trading authorisation"
              subtitle="Multi-step, recorded, revocable"
              action={<StatusBadge status={live.data?.status ?? "not_requested"} />}
            />
            <PanelBody className="space-y-4">
              {live.loading ? (
                <Skeleton className="h-40 w-full" />
              ) : live.data ? (
                <>
                  <div className="rounded-lg border border-warn/30 bg-warn/5 px-3 py-2.5">
                    <p className="flex items-center gap-2 text-xs text-warn">
                      <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                      Real money. Losses can exceed expectations.
                    </p>
                    <p className="mt-1 text-2xs leading-relaxed text-paper-faint">{live.data.note}</p>
                  </div>

                  <div className="space-y-2">
                    {Object.entries(live.data.checklist_items).map(([key, label]) => (
                      <label key={key} className="flex items-start gap-2.5 text-xs leading-relaxed text-paper-muted">
                        <input
                          type="checkbox"
                          checked={Boolean(checklist[key])}
                          onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                          className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-champagne-500"
                        />
                        {label}
                      </label>
                    ))}
                  </div>

                  <label className="flex items-start gap-2.5 rounded-lg border border-line-soft bg-ink-900 px-3 py-2.5 text-xs leading-relaxed text-paper-muted">
                    <input
                      type="checkbox"
                      checked={acknowledged}
                      onChange={(event) => setAcknowledged(event.target.checked)}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-champagne-500"
                    />
                    I have read the risk policy ({live.data.risk_document_version}) and accept it.
                  </label>

                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label="Jurisdiction" htmlFor="jurisdiction" hint="Two-letter country code.">
                      <Input
                        id="jurisdiction"
                        value={jurisdiction}
                        maxLength={2}
                        onChange={(event) => setJurisdiction(event.target.value)}
                      />
                    </Field>
                    <Field label="Authenticator code" htmlFor="totp" hint="Required when MFA is enabled.">
                      <Input id="totp" inputMode="numeric" value={totp} onChange={(event) => setTotp(event.target.value)} />
                    </Field>
                  </div>

                  {confirmationToken ? (
                    <div className="space-y-2 rounded-lg border border-champagne-600/40 bg-champagne-500/[0.06] p-3">
                      <p className="text-xs text-paper">Cooling-off period</p>
                      <p className="text-2xs leading-relaxed text-paper-faint">
                        Confirmation expires {dateTime(live.data.confirm_expires_at)}. Confirming now records your
                        authorisation; it does not place any order.
                      </p>
                      <Textarea readOnly value={confirmationToken} className="min-h-12 text-2xs" />
                      <Button size="sm" onClick={confirmLiveAuthorization} loading={busy}>
                        Confirm authorisation
                      </Button>
                    </div>
                  ) : null}

                  <div className="flex flex-wrap gap-2">
                    <Button
                      onClick={startLiveAuthorization}
                      loading={busy}
                      disabled={!live.data.entitlement || Object.keys(live.data.checklist_items).some((key) => !checklist[key]) || !acknowledged}
                    >
                      Start authorisation
                    </Button>
                    <Button variant="ghost" onClick={revokeLiveAuthorization} disabled={busy || live.data.status === "not_requested"}>
                      Revoke
                    </Button>
                  </div>
                  {!live.data.entitlement ? (
                    <p className="text-2xs text-warn">
                      Your plan is not eligible for live trading. Pro and Elite include the capability; authorisation is
                      still required.
                    </p>
                  ) : null}
                </>
              ) : null}
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader title="Current state" />
            <PanelBody>
              <KeyValue
                items={[
                  { label: "Platform gate", value: live.data?.platform_live_enabled ? <Badge tone="warn">open</Badge> : <Badge tone="neutral">closed</Badge> },
                  { label: "Plan eligible", value: live.data?.entitlement ? "Yes" : "No" },
                  { label: "Authorisation", value: <StatusBadge status={live.data?.status ?? "not_requested"} /> },
                  { label: "Live enabled", value: live.data?.live_enabled ? "Yes" : "No" },
                  { label: "Authorised at", value: dateTime(live.data?.authorized_at ?? null) },
                  { label: "Jurisdiction", value: live.data?.jurisdiction ?? "—" },
                ]}
              />
              <p className="mt-4 text-2xs leading-relaxed text-paper-faint">
                Even with every gate open, each order is evaluated by the risk engine. A rejected order never reaches a
                venue, and the rejection is stored.
              </p>
            </PanelBody>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
