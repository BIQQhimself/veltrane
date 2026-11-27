"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Building2, CreditCard, FileText, Flag, LifeBuoy, Mail, Palette, Share2, Users } from "lucide-react";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth";
import { Wordmark } from "@/components/brand";
import { Badge } from "@/components/ui/badge";
import { KillSwitchControl } from "@/components/app/kill-switch";

const NAV = [
  { href: "/admin", label: "Business overview", icon: Building2 },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/plans", label: "Plans & entitlements", icon: CreditCard },
  { href: "/admin/appearance", label: "Appearance", icon: Palette },
  { href: "/admin/risk", label: "Risk & flags", icon: Flag },
  { href: "/admin/referrals", label: "Referrals", icon: Share2 },
  { href: "/admin/email", label: "Email centre", icon: Mail },
  { href: "/admin/audit", label: "Audit log", icon: FileText },
  { href: "/admin/support", label: "Support", icon: LifeBuoy },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-ink-950">
      {/* A gold hairline marks the operator environment, so it is never mistaken for a customer view. */}
      <div className="h-0.5 w-full bg-gradient-to-r from-champagne-700/70 via-champagne-400/80 to-transparent" />
      <header className="sticky top-0 z-30 border-b border-line-soft bg-ink-950/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Wordmark compact />
            <span className="hidden h-4 w-px bg-line-strong sm:block" />
            <span className="hidden text-2xs uppercase tracking-[0.18em] text-champagne-400 sm:block">
              Command centre
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <KillSwitchControl iconOnly />
            <Badge tone="warn">{user?.staff_role ?? "staff"}</Badge>
            <Link
              href="/app"
              className="flex items-center gap-1.5 rounded-full border border-line-soft px-3 py-1.5 text-2xs text-paper-muted transition hover:border-line-strong hover:text-paper"
            >
              <ArrowLeft className="h-3 w-3" />
              <span className="hidden sm:inline">Workspace</span>
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6 sm:px-6">
        <aside className="hidden w-56 shrink-0 lg:block">
          <nav className="sticky top-20 space-y-0.5" aria-label="Admin">
            {NAV.map((item) => {
              const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs transition",
                    active
                      ? "bg-white/[0.06] text-paper shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
                      : "text-paper-faint hover:bg-white/[0.03] hover:text-paper-muted",
                  )}
                >
                  <item.icon className={cn("h-3.5 w-3.5", active && "text-champagne-400")} aria-hidden />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <p className="mt-6 px-3 text-2xs leading-relaxed text-paper-faint/70">
            Staff actions are audited. Subscriber credentials are never shown in plaintext, to anyone.
          </p>
        </aside>

        <main id="main" className="min-w-0 flex-1">
          <div className="mb-4 flex gap-1 overflow-x-auto lg:hidden">
            {NAV.map((item) => {
              const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "whitespace-nowrap rounded-full border border-line-soft px-3 py-1.5 text-2xs",
                    active ? "border-champagne-500/40 bg-white/[0.06] text-paper" : "text-paper-faint",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
