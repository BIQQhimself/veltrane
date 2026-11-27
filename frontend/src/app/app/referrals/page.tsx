"use client";

import * as React from "react";
import { Check, Copy, Share2, Users } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";

type ReferralStatus = {
  link: string;
  events: { kind: string; created_at: string | null }[];
  note: string;
};

export default function ReferralsPage() {
  const { identity } = useAuth();
  const toast = useToast();
  const status = useApi<ReferralStatus>((signal) => api("/referrals/me", { signal }));
  const [copied, setCopied] = React.useState(false);

  async function copyLink() {
    const link = status.data?.link;
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not copy", "Copy the link from the field instead.");
    }
  }

  async function share() {
    const link = status.data?.link;
    if (!link) return;
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: "VELTRANE", url: link });
        return;
      } catch {
        /* the trader cancelled the share sheet */
      }
    }
    await copyLink();
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Referrals"
        title="Invite traders you would vouch for"
        description="Your link opens the Deriv sign-up page. Commission on that relationship is settled by Deriv under their terms, not by VELTRANE, and we never pay you for referring yourself."
      />

      {status.error ? <ErrorNote message={status.error} onRetry={status.refetch} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <section className="tile tile-sheen p-5" aria-label="Your referral link">
          <h2 className="text-sm font-medium text-paper">Your link</h2>
          {status.loading ? (
            <Skeleton className="mt-3 h-10" />
          ) : (
            <>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <input
                  readOnly
                  value={status.data?.link ?? ""}
                  onFocus={(event) => event.currentTarget.select()}
                  aria-label="Referral link"
                  className="h-10 w-full rounded-lg border border-line-strong bg-obsidian-900 px-3 font-mono text-2xs text-paper-muted"
                />
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={copyLink}>
                    {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
                    <span className="ml-1.5">{copied ? "Copied" : "Copy"}</span>
                  </Button>
                  <Button onClick={share}>
                    <Share2 className="h-3.5 w-3.5" aria-hidden />
                    <span className="ml-1.5">Share</span>
                  </Button>
                </div>
              </div>
              <p className="mt-3 text-3xs leading-relaxed text-paper-faint">{status.data?.note}</p>
              {identity?.public_id ? (
                <p className="mt-2 font-mono text-3xs text-paper-faint">
                  Referrer id {identity.public_id} · attributed by Deriv
                </p>
              ) : null}
            </>
          )}
        </section>

        <section className="tile p-5" aria-label="Referral activity">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
              <Users className="h-4 w-4 text-electric-300" aria-hidden />
              Activity
            </h2>
            <Badge tone="neutral">{status.data?.events.length ?? 0}</Badge>
          </div>
          {status.loading ? (
            <Skeleton className="mt-3 h-24" />
          ) : (status.data?.events.length ?? 0) === 0 ? (
            <div className="mt-3">
              <EmptyState
                title="No referral activity yet"
                description="Clicks and sign-ups through your link appear here. Nothing is reported until Deriv confirms it."
              />
            </div>
          ) : (
            <ul className="mt-3 space-y-2">
              {status.data?.events.map((event, index) => (
                <li
                  key={`${event.kind}-${index}`}
                  className="flex items-center justify-between rounded-lg border border-line-soft bg-obsidian-900/60 px-3 py-2 text-2xs"
                >
                  <span className="text-paper-muted">{titleCase(event.kind)}</span>
                  <span className="text-paper-faint">{dateTime(event.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="tile p-5">
        <h2 className="text-sm font-medium text-paper">How this works, plainly</h2>
        <ul className="mt-3 grid gap-3 text-2xs leading-relaxed text-paper-muted md:grid-cols-3">
          <li>
            <span className="block text-paper">Attribution is Deriv&apos;s.</span>
            A visitor who opens your link is recorded as an opaque id. Deriv decides whether a sign-up is attributed.
          </li>
          <li>
            <span className="block text-paper">We do not promise earnings.</span>
            Commission depends on the referred account&apos;s activity and Deriv&apos;s terms. No figure is estimated or
            projected here.
          </li>
          <li>
            <span className="block text-paper">Self-referral is not allowed.</span>
            Referring your own account breaches the programme and is removed without payment.
          </li>
        </ul>
        <p className="mt-4 text-3xs text-paper-faint">
          Availability and disclosure requirements vary by jurisdiction. Check what applies where you live before
          promoting a link.
        </p>
      </section>
    </div>
  );
}
