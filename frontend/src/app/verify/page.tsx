import type { Metadata } from "next";
import Link from "next/link";
import { Wordmark } from "@/components/brand";
import { AuthRoot } from "@/components/app/gate";
import { VerifyForm } from "./verify-form";

export const metadata: Metadata = { title: "Verify your email" };

export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <main id="main" className="relative flex min-h-screen items-center justify-center px-6 py-12">
      <div className="pointer-events-none absolute inset-0 bg-grid-fade" aria-hidden />
      <div className="relative w-full max-w-sm">
        <Link href="/" className="mb-10 inline-block">
          <Wordmark />
        </Link>
        <h1 className="font-display text-3xl tracking-tight text-paper">Verify your email</h1>
        <p className="mt-2 text-sm text-paper-muted">Confirm the address before signing in.</p>
        <AuthRoot>
          <VerifyForm token={token ?? ""} />
        </AuthRoot>
      </div>
    </main>
  );
}
