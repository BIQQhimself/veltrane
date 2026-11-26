"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

export function VerifyForm({ token }: { token: string }) {
  const [value, setValue] = useState(token);
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">(token ? "busy" : "idle");
  const [error, setError] = useState<string | null>(null);
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || attempted.current) return;
    attempted.current = true;
    void submit(token);
  }, [token]);

  async function submit(candidate: string) {
    setState("busy");
    setError(null);
    try {
      await api("/auth/verify-email", { method: "POST", body: { token: candidate }, retryOnAuth: false });
      setState("done");
    } catch (err) {
      setError(errorMessage(err));
      setState("error");
    }
  }

  if (state === "done") {
    return (
      <div className="mt-8 rounded-xl border border-gain/30 bg-gain/5 p-6">
        <CheckCircle2 className="h-5 w-5 text-gain" aria-hidden />
        <h2 className="mt-3 text-sm font-medium text-paper">Address verified</h2>
        <p className="mt-2 text-xs text-paper-muted">You can sign in and finish setting up your workspace.</p>
        <Link
          href="/login"
          className="mt-4 inline-flex h-10 items-center rounded-lg bg-gradient-to-b from-champagne-400 to-champagne-600 px-4 text-xs font-medium text-ink-950"
        >
          Continue to sign in
        </Link>
      </div>
    );
  }

  return (
    <form
      className="mt-8 space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        void submit(value.trim());
      }}
    >
      <Field label="Verification token" htmlFor="token" hint="Paste the token from your email if the link did not open.">
        <Input id="token" value={value} onChange={(event) => setValue(event.target.value)} required />
      </Field>
      {error ? (
        <p className="rounded-lg border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" fullWidth loading={state === "busy"}>
        Verify address
      </Button>
    </form>
  );
}
