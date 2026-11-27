"use client";

import * as React from "react";
import { ShieldAlert } from "lucide-react";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/**
 * "Kill all AI trading". The server-side switch is what stops orders; this control only
 * flips it, so it works the same whether or not a strategy is running.
 */
export function KillSwitchControl({
  compact = false,
  iconOnly = false,
  className,
}: {
  compact?: boolean;
  iconOnly?: boolean;
  className?: string;
}) {
  const toast = useToast();
  const { refresh } = useAuth();
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("Manual halt from workspace");
  const [busy, setBusy] = React.useState(false);
  const { data, refetch } = useApi<{ kill_switches: Record<string, { engaged?: boolean }> }>((signal) =>
    api("/trading/state", { signal }),
  );
  const engaged = Boolean(data?.kill_switches?.org?.engaged);

  async function toggle() {
    setBusy(true);
    try {
      await api(engaged ? "/trading/kill-switch/release" : "/trading/kill-switch", {
        method: "POST",
        body: { scope: "org", reason },
      });
      toast.success(
        engaged ? "Trading resumed" : "Trading halted",
        engaged ? "Organisation kill switch released." : "No new orders will be accepted.",
      );
      setOpen(false);
      refetch();
      void refresh();
    } catch (error) {
      toast.error("Kill switch failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-xs transition",
          engaged
            ? "border-loss/50 bg-loss/15 text-loss hover:bg-loss/25"
            : "border-line-strong text-paper-muted hover:border-loss/40 hover:text-loss",
          compact && "justify-center px-2",
          iconOnly &&
            "relative h-9 w-9 justify-center rounded-full border-line-soft px-0 text-paper-muted hover:border-loss/40 hover:text-loss",
          engaged && iconOnly && "border-loss/50 bg-loss/15 text-loss",
          className,
        )}
        aria-label={engaged ? "Release the trading kill switch" : "Engage the trading kill switch"}
      >
        <ShieldAlert className={cn("shrink-0", iconOnly ? "h-4 w-4" : "h-4 w-4")} aria-hidden />
        {compact || iconOnly ? null : (
          <span className="min-w-0 flex-1 truncate text-left">
            {engaged ? "Trading halted — release" : "Kill all AI trading"}
          </span>
        )}
        {engaged && !iconOnly ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-loss" aria-hidden /> : null}
        {engaged && iconOnly ? (
          <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-loss" aria-hidden />
        ) : null}
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={engaged ? "Release the kill switch" : "Halt all AI trading for this organisation"}
        description={
          engaged
            ? "Trading resumes only after the reason is recorded in the audit trail."
            : "Every strategy order is refused immediately. Existing contracts stay open — close them deliberately."
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant={engaged ? "success" : "danger"} loading={busy} onClick={toggle}>
              {engaged ? "Release" : "Halt trading"}
            </Button>
          </>
        }
      >
        <Field label="Reason" hint="Recorded with your account and IP address.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} />
        </Field>
      </Dialog>
    </>
  );
}
