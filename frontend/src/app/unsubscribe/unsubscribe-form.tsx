"use client";

import * as React from "react";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";

type Preview = { valid: boolean; promotional: boolean };

/**
 * The unsubscribe page linked from promotional mail. The token is in the query string and
 * the POST only happens when the reader presses the button, so a mail scanner that fetches
 * the link cannot unsubscribe anyone by accident.
 */
export function UnsubscribeForm() {
  const [token, setToken] = React.useState("");
  const [preview, setPreview] = React.useState<Preview | null>(null);
  const [state, setState] = React.useState<"idle" | "busy" | "done" | "error">("idle");
  const [message, setMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    const fromQuery = new URLSearchParams(window.location.search).get("token") ?? "";
    setToken(fromQuery);
    if (!fromQuery) return;
    api<Preview>(`/email/unsubscribe?token=${encodeURIComponent(fromQuery)}`)
      .then(setPreview)
      .catch(() => setPreview({ valid: false, promotional: false }));
  }, []);

  async function confirm() {
    setState("busy");
    setMessage(null);
    try {
      await api("/email/unsubscribe", { method: "POST", body: { token } });
      setState("done");
      setMessage("Promotional email is now off. Security, billing and risk notices still reach you.");
    } catch (error) {
      setState("error");
      setMessage(errorMessage(error));
    }
  }

  if (!token) {
    return (
      <p className="text-sm text-paper-muted">
        This link is incomplete. Open the unsubscribe link from the email again, or turn promotional mail off in
        Settings → Notifications.
      </p>
    );
  }

  if (state === "done") {
    return <p className="text-sm text-gain">{message}</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-paper-muted">
        {preview === null
          ? "Checking this link…"
          : preview.valid
            ? preview.promotional
              ? "Confirm that you no longer want product news and plan announcements."
              : "Promotional email is already off for this address."
            : "This link is not recognised. Nothing has been changed."}
      </p>
      {preview?.valid && preview.promotional ? (
        <Button onClick={confirm} loading={state === "busy"}>
          Unsubscribe from promotional email
        </Button>
      ) : null}
      {message && state === "error" ? <p className="text-2xs text-loss">{message}</p> : null}
      <p className="text-2xs leading-relaxed text-paper-faint">
        Unsubscribing never affects security notices, billing receipts or risk warnings. Those report actions on your
        account and cannot be switched off.
      </p>
    </div>
  );
}
