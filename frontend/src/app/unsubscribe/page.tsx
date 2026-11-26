import type { Metadata } from "next";
import Link from "next/link";
import { Wordmark } from "@/components/brand";
import { UnsubscribeForm } from "./unsubscribe-form";

export const metadata: Metadata = { title: "Email preferences" };

export default function UnsubscribePage() {
  return (
    <main id="main" className="relative flex min-h-screen items-center justify-center px-6 py-12">
      <div className="pointer-events-none absolute inset-0 bg-grid-fade" aria-hidden />
      <div className="relative w-full max-w-md">
        <Link href="/" className="mb-10 inline-block">
          <Wordmark />
        </Link>
        <h1 className="font-display text-3xl tracking-tight text-paper">Email preferences</h1>
        <p className="mt-2 text-sm text-paper-muted">Choose what VELTRANE may send you.</p>
        <div className="mt-6">
          <UnsubscribeForm />
        </div>
      </div>
    </main>
  );
}
