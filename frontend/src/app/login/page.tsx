import type { Metadata } from "next";
import Link from "next/link";
import { Wordmark } from "@/components/brand";
import { AuthRoot } from "@/components/app/gate";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main id="main" className="relative flex min-h-screen items-center justify-center px-6 py-12">
      <div className="pointer-events-none absolute inset-0 bg-grid-fade" aria-hidden />
      <div className="relative w-full max-w-sm">
        <Link href="/" className="mb-10 inline-block">
          <Wordmark />
        </Link>
        <h1 className="font-display text-3xl tracking-tight text-paper">Welcome back</h1>
        <p className="mt-2 text-sm text-paper-muted">Sign in to your trading workspace.</p>
        <AuthRoot><LoginForm /></AuthRoot>
        <p className="mt-8 text-xs text-paper-faint">
          New here?{" "}
          <Link href="/register" className="link-underline text-paper">
            Open an account
          </Link>
        </p>
      </div>
    </main>
  );
}
