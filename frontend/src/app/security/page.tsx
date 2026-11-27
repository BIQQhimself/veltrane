import type { Metadata } from "next";
import { DocList, DocSection, DocShell } from "@/components/marketing/doc-shell";

export const metadata: Metadata = {
  title: "Security",
  description:
    "How VELTRANE handles authentication, tenant isolation, exchange credentials, billing integrity and the gaps that still need independent review.",
};

export default function SecurityPage() {
  return (
    <DocShell
      eyebrow="Security"
      title="Security posture"
      summary="Written to be auditable rather than reassuring. It lists what is implemented, what is assumed, and what still needs independent review."
      version="security-2026-01"
    >
      <DocSection title="What is at risk, and what is not">
        <p>Four assets matter: exchange credentials, trading state, billing state, and operator access.</p>
        <p>
          Client funds are not one of them. VELTRANE never custodies money. Withdrawal permission is
          prohibited by product design, the connection checklist requires you to attest that your key
          is trade-only, and the platform cannot move funds out of an account even if it wanted to.
        </p>
      </DocSection>

      <DocSection title="Authentication">
        <DocList
          items={[
            "Passwords are hashed with argon2id. The minimum is 12 characters with mixed case, a digit and a symbol, enforced server-side.",
            "Email verification is required before sign-in.",
            "TOTP multi-factor authentication is available. The shared secret is encrypted at rest and never returned after setup.",
            "Repeated failed sign-ins lock the account temporarily, and failures are recorded with IP address and user agent.",
            "Access tokens are short-lived JWTs. Refresh tokens rotate on every use and are stored hashed.",
            "Refresh uses an httpOnly, SameSite cookie with a double-submit CSRF token; a refresh without the matching header is rejected.",
            "Signing out revokes the presented token immediately. Signing out everywhere, or changing a password, invalidates every token issued before it.",
            "A production deployment refuses to start with the development secret, without secure cookies, or with the mock payment provider.",
          ]}
        />
      </DocSection>

      <DocSection title="Tenant isolation and staff access">
        <DocList
          items={[
            "Every query is scoped by the organisation on the authenticated session, never by an identifier in the request body.",
            "Requesting another tenant's object returns not-found rather than forbidden, so existence is not disclosed.",
            "Staff endpoints require a staff role: owner for pricing, risk policy, kill switches and role changes; analyst read-only; support limited to reading users and replying to tickets.",
            "A staff member cannot promote anyone to owner, and cannot escalate their own role.",
            "Entitlements are resolved server-side on every request that needs them. Hiding a button is never the control.",
          ]}
        />
      </DocSection>

      <DocSection title="Exchange credentials">
        <DocList
          items={[
            "API keys are encrypted with AES-256-GCM under a per-credential data key, itself encrypted by a master key.",
            "Only a masked hint and a SHA-256 fingerprint are stored in clear.",
            "No endpoint returns secret material, including the admin API. Staff cannot read a subscriber's key in plaintext.",
            "Revoking a connection deletes its credential row; rotating replaces the ciphertext.",
            "Withdrawal permission is never requested.",
          ]}
        />
      </DocSection>

      <DocSection title="Payments">
        <DocList
          items={[
            "Subscription state changes only through a signature-verified payment webhook, never from a browser message.",
            "Webhook events are stored by provider and event identifier under a unique constraint, so a replay returns already-processed instead of charging twice.",
            "Refunds are staff-only, cannot exceed the captured amount, and are audited.",
            "Card data never reaches this system; the payment provider holds it.",
          ]}
        />
      </DocSection>

      <DocSection title="Transport, abuse and audit">
        <DocList
          items={[
            "Security headers include frame denial, content-type sniffing protection, a referrer policy, a permissions policy and HSTS in production. API responses are never cached.",
            "Cross-origin requests are restricted to an explicit allowlist.",
            "Rate limits are enforced per client with tighter budgets on sign-in, registration, password reset and order submission.",
            "Every request body is validated against a bounded schema. Unexpected errors return a generic payload; stack traces are logged, never returned.",
            "Authentication, orders, fills, rejections, connections, billing, consent and configuration changes are written to an append-only audit log in the same transaction as the change.",
          ]}
        />
      </DocSection>

      <DocSection title="Known gaps">
        <p>These are open, and stating them is part of the policy.</p>
        <DocList
          items={[
            "No independent penetration test or code audit has been performed.",
            "No web application firewall or bot mitigation sits in front of the API.",
            "Multi-factor authentication is optional. Staff accounts should be required to use it before a production launch.",
            "Email delivery is a database outbox in this environment; a real transport must be configured and monitored.",
            "There is no anomaly detection on trading behaviour beyond the fraud signals dashboard.",
            "Redis is treated as ephemeral. A Redis loss re-enables previously revoked short-lived tokens until they expire, which the 15-minute access-token lifetime bounds.",
          ]}
        />
      </DocSection>

      <DocSection title="Reporting a vulnerability">
        <p>
          If you believe you have found a security issue, report it privately through support rather
          than in public. Include the steps to reproduce it and what you observed.
        </p>
      </DocSection>
    </DocShell>
  );
}
