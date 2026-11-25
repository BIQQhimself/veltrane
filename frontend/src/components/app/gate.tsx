"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import { AppShell } from "@/components/app/shell";
import { Skeleton } from "@/components/ui/data";

function Gate({ children, admin }: { children: React.ReactNode; admin?: boolean }) {
  const { user, loading, error } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!loading && user && admin && !user.is_staff) router.replace("/app");
  }, [loading, user, admin, router]);

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

  return <AppShell>{children}</AppShell>;
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
