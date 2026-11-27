"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Check, Circle, Lock } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress, Skeleton } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";

type Step = {
  id: number;
  title: string;
  body: string;
  href?: string;
  cta?: string;
  done: boolean;
  locked?: boolean;
};

export default function OnboardingPage() {
  const toast = useToast();
  const { user, entitlements, subscription, refresh } = useAuth();
  const connections = useApi<{ connections: Array<{ id: string; status: string; environment: string }> }>((signal) =>
    api("/connections", { signal }),
  );
  const sessions = useApi<{ sessions: Array<{ id: string; status: string }> }>((signal) => api("/paper-sessions", { signal }));
  const [ackPolicy, setAckPolicy] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const step = user?.onboarding_step ?? 0;
  const connected = (connections.data?.connections ?? []).filter((item) => item.status !== "revoked").length;
  const synced = (connections.data?.connections ?? []).some((item) => item.status === "connected");
  const hasSession = (sessions.data?.sessions ?? []).length > 0;
  const plan = subscription?.plan_code ?? "free";
  const liveEligible = Boolean(entitlements?.features?.live_trading);

  async function advance(next: number, data: Record<string, unknown> = {}) {
    setBusy(true);
    try {
      await api("/users/me/onboarding", { method: "POST", body: { step: next, data } });
      await refresh();
      toast.success("Progress saved");
    } catch (error) {
      toast.error("Could not save progress", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function resendVerification() {
    setBusy(true);
    try {
      const result = await api<{ debug_verification_token?: string }>("/auth/resend-verification", {
        method: "POST",
        body: { email: user?.email },
      });
      if (result.debug_verification_token) {
        toast.info("Development token issued", `Open /verify?token=${result.debug_verification_token.slice(0, 12)}…`);
      } else {
        toast.success("Verification queued", "Check your inbox.");
      }
    } catch (error) {
      toast.error("Could not resend", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const steps: Step[] = [
    {
      id: 1,
      title: "Verify your email",
      body: "Confirmation protects account recovery and billing correspondence.",
      done: Boolean(user?.email_verified),
      cta: "Resend verification",
    },
    {
      id: 2,
      title: "Secure the account",
      body: "Enable two-factor authentication. It is required before live authorisation.",
      href: "/app/settings",
      cta: "Security settings",
      done: Boolean(user?.mfa_enabled),
    },
    {
      id: 3,
      title: "Choose a plan",
      body: "Free is fully usable in simulation. Paid tiers unlock more strategies, backtests and limits.",
      href: "/app/billing",
      cta: "Compare plans",
      done: plan !== "free",
    },
    {
      id: 4,
      title: "Connect an account",
      body: "Start with the simulation venue, or connect a crypto exchange read-only.",
      href: "/app/accounts",
      cta: "Connected accounts",
      done: connected > 0,
    },
    {
      id: 5,
      title: "Sync read-only data",
      body: "Balances and positions are pulled from the venue. Credentials stay encrypted.",
      href: "/app/accounts",
      cta: "Run a sync",
      done: synced,
    },
    {
      id: 6,
      title: "Set risk preferences",
      body: "Drawdown tolerance, position sizing and horizon. These set defaults, not limits.",
      href: "/app/settings",
      cta: "Risk preferences",
      done: step >= 6,
    },
    {
      id: 7,
      title: "Configure a strategy",
      body: "Read the specification, then start a paper session on the instrument you follow.",
      href: "/app/strategies",
      cta: "Strategy library",
      done: hasSession,
    },
    {
      id: 8,
      title: "Place a paper trade",
      body: "Simulated execution uses the same risk engine as live. Try a rejected order on purpose.",
      href: "/app/terminal",
      cta: "Open terminal",
      done: step >= 8,
    },
    {
      id: 9,
      title: "Read the risk policy",
      body: "Understand what the engine enforces, and what it cannot protect you from.",
      done: step >= 9,
    },
    {
      id: 10,
      title: "Authorise live trading",
      body: "Only for eligible plans. Requires every checklist item, MFA and a cooling-off period.",
      href: "/app/settings",
      cta: "Live authorisation",
      done: step >= 10,
      locked: !liveEligible,
    },
  ];

  const completed = steps.filter((item) => item.done).length;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Setup"
        title="Onboarding"
        description="Ten steps from account to autonomous execution. You can stop at simulation for as long as you like — nothing here pushes you toward live trading."
        action={<Badge tone="gold">{completed}/10 complete</Badge>}
      />

      <Panel>
        <PanelBody>
          <div className="flex items-center justify-between text-xs text-paper-muted">
            <span>Progress</span>
            <span className="num">{Math.round((completed / 10) * 100)}%</span>
          </div>
          <div className="mt-2">
            <Progress value={completed} max={10} />
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Steps" subtitle="Completed steps are detected from your account state, not clicks" />
        {connections.loading ? (
          <div className="p-5">
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <ol className="divide-y divide-line-soft/70">
            {steps.map((item) => (
              <li key={item.id} className="flex flex-wrap items-start justify-between gap-4 px-5 py-4">
                <div className="flex min-w-0 items-start gap-3">
                  <span
                    className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-2xs ${
                      item.done
                        ? "border-gain/40 bg-gain/10 text-gain"
                        : item.locked
                          ? "border-line-strong text-paper-faint"
                          : "border-line-strong text-paper-muted"
                    }`}
                  >
                    {item.done ? <Check className="h-3 w-3" /> : item.locked ? <Lock className="h-3 w-3" /> : <Circle className="h-2 w-2" />}
                  </span>
                  <div className="min-w-0">
                    <p className={`text-sm ${item.done ? "text-paper-muted" : "text-paper"}`}>
                      {item.id}. {item.title}
                    </p>
                    <p className="mt-0.5 text-xs leading-relaxed text-paper-faint">{item.body}</p>
                    {item.locked ? (
                      <p className="mt-1 text-2xs text-warn">Requires the Pro plan or above.</p>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {item.done ? (
                    <Badge tone="gain">done</Badge>
                  ) : item.id === 1 ? (
                    <Button size="sm" variant="secondary" onClick={resendVerification} disabled={busy}>
                      {item.cta}
                    </Button>
                  ) : item.id === 9 ? (
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-1.5 text-2xs text-paper-muted">
                        <input
                          type="checkbox"
                          checked={ackPolicy}
                          onChange={(event) => setAckPolicy(event.target.checked)}
                          className="h-3.5 w-3.5 accent-champagne-500"
                        />
                        I have read it
                      </label>
                      <Button size="sm" variant="secondary" disabled={!ackPolicy || busy} onClick={() => advance(9, { risk_policy_read: true })}>
                        Mark read
                      </Button>
                    </div>
                  ) : item.href ? (
                    <Link href={item.href}>
                      <Button size="sm" variant="secondary">
                        {item.cta}
                        <ArrowRight className="h-3 w-3" />
                      </Button>
                    </Link>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel>
          <PanelBody className="space-y-2">
            <p className="label">What stays locked</p>
            <p className="text-xs leading-relaxed text-paper-muted">
              Live execution requires: an eligible plan, a trade-enabled connection, explicit authorisation, a passing
              risk evaluation for each order, and an operator-enabled platform gate. No single step unlocks the rest.
            </p>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody className="space-y-2">
            <p className="label">Current plan</p>
            <p className="text-sm text-paper">{titleCase(plan)}</p>
            <p className="text-2xs text-paper-faint">
              Connections limit {entitlements?.limits?.max_connections ?? "—"} · demo executions{" "}
              {entitlements?.limits?.max_daily_demo_executions ?? "unlimited"} per day
            </p>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
