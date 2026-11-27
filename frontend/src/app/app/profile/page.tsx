"use client";

import * as React from "react";
import Link from "next/link";
import { Check, Copy, ShieldCheck, ShieldAlert, UserRound } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { usePresence } from "@/lib/presence";
import { errorMessage } from "@/lib/api";
import { automationSummary, capLabel, tierFor } from "@/lib/membership";
import { dateOnly } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { IdentityAvatar, TierBadge } from "@/components/app/tier-badge";
import { cn } from "@/lib/cn";

const COLORS = ["#C8A96A", "#7F9F8C", "#8C7BB0", "#B06A6A", "#6E8CA8", "#A98F6B", "#7E9E9C", "#9B8AA6"] as const;
const DEFAULT_COLOR: string = COLORS[0];

export default function ProfilePage() {
  const { user, identity, entitlements, subscription, updateProfile } = useAuth();
  const { automation } = usePresence();
  const toast = useToast();

  const plan = entitlements?.plan_code ?? subscription?.plan_code ?? "free";
  const tier = tierFor(plan);
  const [name, setName] = React.useState("");
  const [color, setColor] = React.useState<string>(DEFAULT_COLOR);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (identity) {
      setName(identity.display_name);
      setColor(identity.avatar_color);
    }
  }, [identity]);

  const dirty = Boolean(identity) && (name.trim() !== identity?.display_name || color !== identity?.avatar_color);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateProfile({ display_name: name.trim(), avatar_color: color });
      toast.success("Profile updated", "Your display name and avatar are saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function copyId() {
    if (!identity?.public_id) return;
    try {
      await navigator.clipboard.writeText(identity.public_id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not copy", "Select the account id and copy it manually.");
    }
  }

  const summary = automationSummary(tier, automation);

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Profile"
        title="Your trader identity"
        description="The display name and avatar are how you appear in this workspace and on support tickets. They do not change your legal name, your billing details or what your plan permits."
      />

      <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        <section className="tile tile-sheen" aria-label="Identity">
          <div className="flex items-center gap-4 border-b border-line-soft p-5">
            <IdentityAvatar name={name || identity?.display_name || "Trader"} color={color} planCode={plan} size={56} />
            <div className="min-w-0">
              <p className="truncate font-display text-lg text-paper">{identity?.display_name ?? "Trader"}</p>
              <p className="truncate text-2xs text-paper-faint">{user?.email}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <TierBadge planCode={plan} size="xs" />
                {identity?.public_id ? (
                  <button
                    type="button"
                    onClick={copyId}
                    className="inline-flex items-center gap-1 rounded-full border border-line-soft px-2 py-0.5 font-mono text-3xs text-paper-faint transition hover:border-line-strong hover:text-paper-muted"
                    aria-label={`Copy account id ${identity.public_id}`}
                  >
                    {copied ? <Check className="h-2.5 w-2.5 text-gain" aria-hidden /> : <Copy className="h-2.5 w-2.5" aria-hidden />}
                    {identity.public_id}
                  </button>
                ) : null}
              </div>
            </div>
          </div>

          <form onSubmit={save} className="space-y-4 p-5">
            <Field
              label="Display name"
              htmlFor="display_name"
              hint="Shown in the workspace and to support. 2–40 characters."
              error={error ?? undefined}
            >
              <Input
                id="display_name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={40}
                autoComplete="nickname"
                required
              />
            </Field>

            <fieldset>
              <legend className="mb-2 text-xs font-medium text-paper-muted">Avatar colour</legend>
              <div className="flex flex-wrap gap-2">
                {COLORS.map((swatch) => (
                  <button
                    key={swatch}
                    type="button"
                    onClick={() => setColor(swatch)}
                    aria-label={`Use colour ${swatch}`}
                    aria-pressed={color.toLowerCase() === swatch.toLowerCase()}
                    className={cn(
                      "h-8 w-8 rounded-full border-2 transition",
                      color.toLowerCase() === swatch.toLowerCase()
                        ? "border-paper"
                        : "border-transparent hover:border-line-strong",
                    )}
                    style={{ background: swatch }}
                  />
                ))}
              </div>
            </fieldset>

            <div className="flex items-center gap-2">
              <Button type="submit" loading={saving} disabled={!dirty}>
                Save profile
              </Button>
              {dirty ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setName(identity?.display_name ?? "");
                    setColor(identity?.avatar_color ?? DEFAULT_COLOR);
                    setError(null);
                  }}
                >
                  Reset
                </Button>
              ) : null}
            </div>
          </form>
        </section>

        <div className="space-y-4">
          <section className="tile p-5" aria-label="Membership summary">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-paper">Membership</h2>
              <Link href="/app/membership" className="text-2xs text-champagne-600 hover:text-champagne-600">
                Manage →
              </Link>
            </div>
            <p className="mt-3 text-2xs text-paper-muted">
              {tier.badge} <span className="text-paper">{tier.label}</span> · {capLabel(tier, automation?.used_today)}
            </p>
            <p className="mt-2 flex items-center gap-2 text-2xs text-paper-faint">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  summary.tone === "gain" ? "bg-gain" : summary.tone === "warn" ? "bg-warn" : "bg-paper-faint",
                )}
                aria-hidden
              />
              {summary.title}
            </p>
          </section>

          <section className="tile p-5" aria-label="Security">
            <h2 className="text-sm font-medium text-paper">Security</h2>
            <ul className="mt-3 space-y-2.5 text-2xs">
              <li className="flex items-start gap-2">
                {user?.mfa_enabled ? (
                  <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gain" aria-hidden />
                ) : (
                  <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" aria-hidden />
                )}
                <span className="text-paper-muted">
                  Two-factor authentication is {user?.mfa_enabled ? "enabled" : "not enabled"}.
                  {user?.mfa_enabled ? "" : " Add it before enabling live trading."}
                </span>
              </li>
              <li className="flex items-start gap-2">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gain" aria-hidden />
                <span className="text-paper-muted">
                  Email {user?.email_verified ? "verified" : "not verified"} on {dateOnly(user?.created_at)}.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <UserRound className="mt-0.5 h-3.5 w-3.5 shrink-0 text-paper-faint" aria-hidden />
                <span className="text-paper-muted">
                  Account status: <Badge tone={user?.status === "active" ? "gain" : "warn"}>{user?.status}</Badge>
                </span>
              </li>
            </ul>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                href="/app/settings"
                className="inline-flex items-center rounded-lg border border-line-strong px-3 py-2 text-2xs text-paper-muted transition hover:bg-obsidian-800 hover:text-paper"
              >
                Password & MFA
              </Link>
              <Link
                href="/app/support"
                className="inline-flex items-center rounded-lg border border-line-strong px-3 py-2 text-2xs text-paper-muted transition hover:bg-obsidian-800 hover:text-paper"
              >
                Contact support
              </Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
