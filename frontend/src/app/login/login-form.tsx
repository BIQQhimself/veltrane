"use client";

import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

export function LoginForm() {
  const { login, verifyMfa } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function enterWorkspace() {
    // A full document load, so the workspace boots from the server with the new session and its own
    // page metadata, instead of carrying the sign-in title into the app.
    window.location.assign("/app");
  }

  async function submitCredentials(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await login(email, password);
      if (result.mfaRequired && result.mfaToken) {
        setMfaToken(result.mfaToken);
      } else {
        enterWorkspace();
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitMfa(event: React.FormEvent) {
    event.preventDefault();
    if (!mfaToken) return;
    setBusy(true);
    setError(null);
    try {
      await verifyMfa(mfaToken, code.trim());
      enterWorkspace();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (mfaToken) {
    return (
      <form onSubmit={submitMfa} className="mt-8 space-y-4">
        <Field label="Authentication code" htmlFor="code" hint="Six digits from your authenticator app, or a recovery code.">
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            value={code}
            onChange={(event) => setCode(event.target.value)}
            required
          />
        </Field>
        {error ? (
          <p className="rounded-lg border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss" role="alert">
            {error}
          </p>
        ) : null}
        <Button type="submit" fullWidth loading={busy}>
          Verify and continue
        </Button>
        <button
          type="button"
          onClick={() => {
            setMfaToken(null);
            setCode("");
          }}
          className="w-full text-center text-xs text-paper-faint transition hover:text-paper"
        >
          Use a different account
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={submitCredentials} className="mt-8 space-y-4">
      <Field label="Email" htmlFor="email">
        <Input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
        />
      </Field>
      <Field label="Password" htmlFor="password">
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>
      {error ? (
        <p className="rounded-lg border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" fullWidth loading={busy}>
        Sign in
        <ArrowRight className="h-4 w-4" />
      </Button>
    </form>
  );
}
