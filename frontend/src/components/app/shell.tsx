"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  CreditCard,
  Gauge,
  LayoutDashboard,
  LineChart,
  LogOut,
  Menu,
  Plug,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Wallet,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { Wordmark, Monogram } from "@/components/brand";
import { initials } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { NotificationsResponse } from "@/lib/types";

const NAV = [
  { href: "/app", label: "Overview", icon: LayoutDashboard },
  { href: "/app/terminal", label: "Trading terminal", icon: Activity },
  { href: "/app/markets", label: "Markets", icon: LineChart },
  { href: "/app/strategies", label: "Strategies", icon: Sparkles },
  { href: "/app/accounts", label: "Connected accounts", icon: Plug },
  { href: "/app/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/app/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/app/notifications", label: "Notifications", icon: Bell },
  { href: "/app/billing", label: "Billing", icon: CreditCard },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

function NavLinks({ onNavigate, unread }: { onNavigate?: () => void; unread: number }) {
  const pathname = usePathname();
  return (
    <nav className="space-y-0.5" aria-label="Workspace">
      {NAV.map((item) => {
        const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-lg px-3 py-2 text-xs transition-colors",
              active ? "bg-ink-800 text-paper" : "text-paper-faint hover:bg-ink-850 hover:text-paper-muted",
            )}
          >
            <item.icon className={cn("h-4 w-4", active ? "text-champagne-400" : "text-paper-faint/80")} aria-hidden />
            <span className="flex-1">{item.label}</span>
            {item.href === "/app/notifications" && unread > 0 ? (
              <span className="rounded-full bg-champagne-500/20 px-1.5 py-0.5 text-2xs text-champagne-300">{unread}</span>
            ) : null}
            {active ? <span className="h-1 w-1 rounded-full bg-champagne-500" /> : null}
          </Link>
        );
      })}
    </nav>
  );
}

function KillSwitchControl() {
  const toast = useToast();
  const { refresh } = useAuth();
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("Manual halt from workspace");
  const [busy, setBusy] = React.useState(false);
  const { data, refetch } = useApi<{ kill_switches: Record<string, { engaged?: boolean }> }>((signal) =>
    api("/trading/state", { signal }),
  );
  const engaged = Boolean(data?.kill_switches?.org?.engaged);

  async function toggle() {
    setBusy(true);
    try {
      await api(engaged ? "/trading/kill-switch/release" : "/trading/kill-switch", {
        method: "POST",
        body: { scope: "org", reason },
      });
      toast.success(engaged ? "Trading resumed" : "Trading halted", engaged ? "Organisation kill switch released." : "No new orders will be accepted.");
      setOpen(false);
      refetch();
      void refresh();
    } catch (error) {
      toast.error("Kill switch failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-xs transition",
          engaged
            ? "border-loss/40 bg-loss/10 text-loss hover:bg-loss/20"
            : "border-line-strong text-paper-muted hover:border-loss/40 hover:text-loss",
        )}
      >
        <ShieldAlert className="h-4 w-4" aria-hidden />
        {engaged ? "Trading halted — release" : "Kill all AI trading"}
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={engaged ? "Release the kill switch" : "Halt all trading for this organisation"}
        description={
          engaged
            ? "Trading resumes only after the reason is recorded in the audit trail."
            : "Every strategy order is refused immediately. Existing positions stay open — close them deliberately."
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant={engaged ? "success" : "danger"} loading={busy} onClick={toggle}>
              {engaged ? "Release" : "Halt trading"}
            </Button>
          </>
        }
      >
        <Field label="Reason" hint="Recorded with your account and IP address.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} />
        </Field>
      </Dialog>
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, entitlements, subscription, platform, logout } = useAuth();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const notifications = useApi<NotificationsResponse>((signal) => api("/notifications", { signal, query: { limit: 20 } }));
  const unread = notifications.data?.unread_count ?? 0;

  const plan = entitlements?.plan_code ?? subscription?.plan_code ?? "free";

  return (
    <div className="min-h-screen bg-ink-950">
      <div className="flex min-h-screen">
        <aside className="hidden w-60 shrink-0 flex-col border-r border-line-soft bg-ink-900/60 px-3 py-5 lg:flex">
          <Link href="/app" className="mb-6 px-2">
            <Wordmark />
          </Link>
          <div className="mb-4 rounded-lg border border-line-soft bg-ink-850 px-3 py-2.5">
            <div className="flex items-center justify-between">
              <span className="label">Plan</span>
              <Badge tone="gold">{plan}</Badge>
            </div>
            <p className="mt-2 text-2xs leading-relaxed text-paper-faint">
              {platform?.live_trading_enabled ? "Platform execution gate open" : "Live execution disabled platform-wide"}
            </p>
          </div>
          <NavLinks unread={unread} />
          <div className="mt-auto space-y-2 pt-4">
            {user?.is_staff ? (
              <Link
                href="/admin"
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-champagne-300 transition hover:bg-ink-850"
              >
                <Gauge className="h-4 w-4" aria-hidden />
                Admin command centre
              </Link>
            ) : null}
            <KillSwitchControl />
            <p className="px-2 text-2xs leading-relaxed text-paper-faint/70">
              VELTRANE never holds your funds. Simulated results are not predictions.
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-line-soft bg-ink-950/85 px-4 backdrop-blur-md sm:px-6">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                className="rounded-md p-1.5 text-paper-muted transition hover:bg-ink-800 lg:hidden"
                aria-label="Open navigation"
              >
                <Menu className="h-5 w-5" />
              </button>
              <span className="text-xs text-paper-faint lg:hidden">
                <Wordmark compact />
              </span>
              <div className="hidden items-center gap-2 text-2xs text-paper-faint sm:flex">
                <ShieldCheck className="h-3.5 w-3.5 text-gain/70" aria-hidden />
                Paper mode available · live gated
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="/app/notifications"
                className="relative rounded-md p-2 text-paper-muted transition hover:bg-ink-800 hover:text-paper"
                aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
              >
                <Bell className="h-4 w-4" />
                {unread > 0 ? (
                  <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-champagne-400" />
                ) : null}
              </Link>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setMenuOpen((open) => !open)}
                  aria-expanded={menuOpen}
                  className="flex items-center gap-2 rounded-lg border border-line-soft px-2 py-1.5 text-xs text-paper-muted transition hover:border-line-strong hover:text-paper"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-md bg-ink-750 text-2xs text-paper">
                    {initials(user?.full_name ?? "V")}
                  </span>
                  <span className="hidden max-w-[10rem] truncate sm:block">{user?.full_name}</span>
                </button>
                {menuOpen ? (
                  <div
                    className="absolute right-0 top-11 z-40 w-56 rounded-lg border border-line-strong bg-ink-850 p-1 shadow-lift"
                    onMouseLeave={() => setMenuOpen(false)}
                  >
                    <div className="px-3 py-2">
                      <p className="truncate text-xs text-paper">{user?.full_name}</p>
                      <p className="truncate text-2xs text-paper-faint">{user?.email}</p>
                    </div>
                    <div className="my-1 h-px bg-line-soft" />
                    <Link href="/app/settings" className="block rounded-md px-3 py-2 text-xs text-paper-muted hover:bg-ink-800">
                      Account settings
                    </Link>
                    <Link href="/app/billing" className="block rounded-md px-3 py-2 text-xs text-paper-muted hover:bg-ink-800">
                      Billing & plan
                    </Link>
                    <button
                      type="button"
                      onClick={async () => {
                        await logout();
                        router.push("/login");
                      }}
                      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-paper-muted hover:bg-ink-800"
                    >
                      <LogOut className="h-3.5 w-3.5" aria-hidden />
                      Sign out
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          </header>

          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:py-8">
            {children}
          </main>
        </div>
      </div>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink-950/80 backdrop-blur-sm" onClick={() => setMobileOpen(false)} aria-hidden />
          <div className="relative flex h-full w-72 flex-col border-r border-line-strong bg-ink-900 px-3 py-5">
            <div className="mb-6 flex items-center justify-between px-2">
              <Wordmark />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="rounded-md p-1.5 text-paper-faint hover:bg-ink-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <NavLinks unread={unread} onNavigate={() => setMobileOpen(false)} />
            <div className="mt-auto space-y-2 pt-4">
              <KillSwitchControl />
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  router.push("/login");
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-paper-muted hover:bg-ink-800"
              >
                <LogOut className="h-4 w-4" aria-hidden />
                Sign out
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="hidden" aria-hidden>
        <Monogram />
      </div>
    </div>
  );
}
