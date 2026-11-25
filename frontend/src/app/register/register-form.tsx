"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, MailCheck } from "lucide-react";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";

const COUNTRIES = [
  ["GB", "United Kingdom"],
  ["US", "United States"],
  ["DE", "Germany"],
  ["FR", "France"],
  ["NL", "Netherlands"],
  ["ES", "Spain"],
  ["IT", "Italy"],
  ["CH", "Switzerland"],
  ["AE", "United Arab Emirates"],
  ["SG", "Singapore"],
  ["AU", "Australia"],
  ["CA", "Canada"],
  ["ZA", "South Africa"],
  ["BR", "Brazil"],
  ["IN", "India"],
  ["JP", "Japan"],
] as const;

export function RegisterForm() {
  const { register } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [country, setCountry] = useState("GB");
  const [password, setPassword] = useState("");
  const [accept, setAccept] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ email: string; debugToken?: string } | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await register({
        email,
        password,
        full_name: fullName,
        country,
        accept_terms: accept,
        terms_version: "terms-2026-01",
      });
      setDone(result);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="mt-8 rounded-xl border border-line bg-ink-850 p-6">
        <MailCheck className="h-5 w-5 text-champagne-400" aria-hidden />
        <h2 className="mt-3 text-sm font-medium text-paper">Check your inbox</h2>
        <p className="mt-2 text-xs leading-relaxed text-paper-muted">
          We sent a verification link to <span className="text-paper">{done.email}</span>. Verify the address,
          then sign in to continue onboarding.
        </p>
        {done.debugToken ? (
          <div className="mt-4 rounded-lg border border-warn/30 bg-warn/5 p-3">
            <p className="text-2xs uppercase tracking-label text-warn">Development only</p>
            <p className="mt-1 text-xs leading-relaxed text-paper-muted">
              Email delivery is not configured in this environment, so the token is exposed here.
            </p>
            <Link
              href={`/verify?token=${encodeURIComponent(done.debugToken)}`}
              className="mt-2 inline-flex items-center gap-1 text-xs text-paper underline decoration-line-strong underline-offset-4"
            >
              Verify now <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        ) : null}
        <Link href="/login" className="mt-5 inline-block text-xs text-paper-faint transition hover:text-paper">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="mt-8 space-y-4">
      <Field label="Full name" htmlFor="full_name">
        <Input
          id="full_name"
          autoComplete="name"
          required
          minLength={2}
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
        />
      </Field>
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
      <Field label="Country of residence" htmlFor="country" hint="Used for eligibility and jurisdiction controls.">
        <Select id="country" value={country} onChange={(event) => setCountry(event.target.value)}>
          {COUNTRIES.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Password" htmlFor="password" hint="At least 12 characters. Length beats complexity.">
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>
      <label className="flex items-start gap-3 text-xs leading-relaxed text-paper-muted">
        <input
          type="checkbox"
          checked={accept}
          onChange={(event) => setAccept(event.target.checked)}
          className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-line-strong bg-ink-900 accent-champagne-500"
          required
        />
        <span>
          I accept the terms of service and privacy policy, and I understand that trading involves risk of
          loss and that simulated results do not predict live results.
        </span>
      </label>
      {error ? (
        <p className="rounded-lg border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" fullWidth loading={busy} disabled={!accept}>
        Create account
        <ArrowRight className="h-4 w-4" />
      </Button>
    </form>
  );
}
