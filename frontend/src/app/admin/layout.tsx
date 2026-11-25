"use client";

import { AdminGate } from "@/components/app/gate";
import { AdminShell } from "@/components/app/admin-shell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <AdminShell>{children}</AdminShell>
    </AdminGate>
  );
}
