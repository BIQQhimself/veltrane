"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import { PresenceProvider } from "@/lib/presence";
import { AppShell } from "@/components/app/shell";
import { Skeleton } from "@/components/ui/data";

function Gate({ children, admin }: { children: React.ReactNode; admin?: boolean }) {
  const { user, loading, error } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-6 py-16">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
        {error ? <p className="text-xs text-loss">{error}</p> : null}
      </div>
    );
  }

  if (admin && !user.is_staff) {
    return (
      <main className="mx-auto flex min-h-[70vh] max-w-lg flex-col items-center justify-center px-6 text-center">
        <p className="text-2xs uppercase tracking-label text-paper-faint">Owner access only</p>
        <h1 className="mt-2 font-display text-2xl font-semibold text-paper">This account is not staff</h1>
        <p className="mt-3 text-xs leading-relaxed text-paper-muted">
          The command centre is limited to VELTRANE staff accounts. The API enforces the same rule on its own, so a
          direct request from this account is refused whether or not the page renders.
        </p>
        <Link href="/app" className="mt-5 text-xs text-champagne-600 hover:text-champagne-600">
          Back to the workspace →
        </Link>
      </main>
    );
  }

  // The command centre brings its own frame; nesting it inside the workspace shell would
  // stack two navigation bars and two kill switches.
  if (admin) return <>{children}</>;

  return (
    <PresenceProvider>
      <AppShell>{children}</AppShell>
    </PresenceProvider>
  );
}

export function AppGate({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <Gate>{children}</Gate>
    </AuthProvider>
  );
}

export function AdminGate({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <Gate admin>{children}</Gate>
    </AuthProvider>
  );
}

export function AuthRoot({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
