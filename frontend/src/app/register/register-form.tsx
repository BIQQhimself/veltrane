"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, MailCheck } from "lucide-react";
import { ApiError, errorMessage, fieldErrors } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { visitorId } from "@/lib/referral";
import { PASSWORD_HINT, PASSWORD_RULES, emailProblem, normalizeEmail, passwordIssues } from "@/lib/validation";
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
  const [fields, setFields] = useState<Record<string, string>>({});
  const [done, setDone] = useState<{ email: string; debugToken?: string } | null>(null);

  function clearField(name: string) {
    setFields((current) => {
      if (!current[name]) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setFields({});

    // Cheap checks first: the API rejects these too, but only after a round trip.
    const problems: Record<string, string> = {};
    const emailIssue = emailProblem(email);
    if (emailIssue) problems.email = emailIssue;
    if (passwordIssues(password).length > 0) problems.password = "The password does not meet all the rules below.";
    if (Object.keys(problems).length > 0) {
      setFields(problems);
      return;
    }

    setBusy(true);
    try {
      const result = await register({
        email: normalizeEmail(email),
        password,
        full_name: fullName.trim(),
        country,
        accept_terms: accept,
        terms_version: "terms-2026-01",
        // Attributes the signup to the referral visit, if this browser arrived through one.
        referral_visitor_id: visitorId(),
      });
      setDone(result);
    } catch (err) {
      // 422 answers carry the failing field; 409 and weak-password answers name one field
      // in their code. Anything else stays a form-level message.
      const perField = fieldErrors(err);
      if (err instanceof ApiError && err.code === "email_in_use") perField.email = err.message;
      if (err instanceof ApiError && err.code === "weak_password") perField.password = err.message;
      if (Object.keys(perField).length > 0) setFields(perField);
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="mt-8 rounded-xl border border-line bg-ink-850 p-6">
        <MailCheck className="h-5 w-5 text-champagne-600" aria-hidden />
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
      <Field label="Full name" htmlFor="full_name" error={fields.full_name}>
        <Input
          id="full_name"
          autoComplete="name"
          required
          minLength={2}
          value={fullName}
          aria-invalid={Boolean(fields.full_name)}
          onChange={(event) => {
            setFullName(event.target.value);
            clearField("full_name");
          }}
        />
      </Field>
      <Field label="Email" htmlFor="email" error={fields.email}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          aria-invalid={Boolean(fields.email)}
          onChange={(event) => {
            setEmail(event.target.value);
            clearField("email");
          }}
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
      <Field label="Password" htmlFor="password" hint={PASSWORD_HINT} error={fields.password}>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          value={password}
          aria-invalid={Boolean(fields.password)}
          aria-describedby="password-rules"
          onChange={(event) => {
            setPassword(event.target.value);
            clearField("password");
          }}
        />
      </Field>
      {password ? (
        <ul id="password-rules" className="space-y-1 text-xs text-paper-faint" aria-live="polite">
          {PASSWORD_RULES.map((rule) => {
            const met = rule.test(password);
            return (
              <li key={rule.id} className={met ? "text-gain" : "text-paper-faint"}>
                {met ? "✓" : "•"} {rule.label}
              </li>
            );
          })}
        </ul>
      ) : null}
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
