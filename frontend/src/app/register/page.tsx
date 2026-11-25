import type { Metadata } from "next";
import Link from "next/link";
import { Wordmark } from "@/components/brand";
import { AuthRoot } from "@/components/app/gate";
import { RegisterForm } from "./register-form";

export const metadata: Metadata = { title: "Create your account" };

export default function RegisterPage() {
  return (
    <main id="main" className="relative flex min-h-screen items-center justify-center px-6 py-12">
      <div className="pointer-events-none absolute inset-0 bg-grid-fade" aria-hidden />
      <div className="relative w-full max-w-md">
        <Link href="/" className="mb-10 inline-block">
          <Wordmark />
        </Link>
        <h1 className="font-display text-3xl tracking-tight text-paper">Open a workspace</h1>
        <p className="mt-2 text-sm leading-relaxed text-paper-muted">
          Start on the Free tier with read-only connections and simulated execution. No card, no custody,
          no live orders.
        </p>
        <AuthRoot><RegisterForm /></AuthRoot>
        <p className="mt-8 text-xs text-paper-faint">
          Already have an account?{" "}
          <Link href="/login" className="link-underline text-paper">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
