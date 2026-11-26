"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  ChevronDown,
  CreditCard,
  Gauge,
  LayoutDashboard,
  LineChart,
  LogOut,
  Menu,
  Plug,
  Search,
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
import { Wordmark, BrandMark } from "@/components/brand";
import { initials } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { NotificationsResponse } from "@/lib/types";

const PRIMARY = [
  { href: "/app", label: "Overview", icon: LayoutDashboard },
  { href: "/app/terminal", label: "Terminal", icon: Activity },
  { href: "/app/markets", label: "Markets", icon: LineChart },
  { href: "/app/strategies", label: "Strategies", icon: Sparkles },
  { href: "/app/copilot", label: "Copilot", icon: Bot },
];

const SECONDARY = [
  { href: "/app/accounts", label: "Connected accounts", icon: Plug },
  { href: "/app/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/app/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/app/notifications", label: "Notifications", icon: Bell },
  { href: "/app/billing", label: "Billing", icon: CreditCard },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

const MOBILE_TABS = [
  { href: "/app", label: "Home", icon: LayoutDashboard },
  { href: "/app/markets", label: "Markets", icon: LineChart },
  { href: "/app/terminal", label: "Trade", icon: Activity, accent: true },
  { href: "/app/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/app/settings", label: "More", icon: Menu },
];

function useActive(pathname: string) {
  return React.useCallback(
    (href: string) => (href === "/app" ? pathname === "/app" : pathname.startsWith(href)),
    [pathname],
  );
}

function NavItem({
  item,
  active,
  unread,
  onNavigate,
}: {
  item: { href: string; label: string; icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }> };
  active: boolean;
  unread?: number;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-xs transition-colors",
        active
          ? "bg-electric-500/10 text-paper shadow-[inset_0_0_0_1px_rgba(46,123,255,0.25)]"
          : "text-paper-faint hover:bg-obsidian-800 hover:text-paper-muted",
      )}
    >
      {active ? (
        <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-electric-400" aria-hidden />
      ) : null}
      <item.icon className={cn("h-4 w-4", active ? "text-electric-300" : "text-paper-faint/80")} aria-hidden />
      <span className="flex-1">{item.label}</span>
      {item.href === "/app/notifications" && unread ? (
        <span className="rounded-full bg-electric-500/20 px-1.5 py-0.5 text-2xs text-electric-200">{unread}</span>
      ) : null}
    </Link>
  );
}

function KillSwitchControl({ compact = false }: { compact?: boolean }) {
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
      toast.success(
        engaged ? "Trading resumed" : "Trading halted",
        engaged ? "Organisation kill switch released." : "No new orders will be accepted.",
      );
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
            ? "border-loss/50 bg-loss/15 text-loss hover:bg-loss/25"
            : "border-line-strong text-paper-muted hover:border-loss/40 hover:text-loss",
          compact && "justify-center px-2",
        )}
        aria-label={engaged ? "Release the trading kill switch" : "Engage the trading kill switch"}
      >
        <ShieldAlert className="h-4 w-4" aria-hidden />
        {compact ? null : <span className="flex-1 text-left">{engaged ? "Trading halted — release" : "Kill all trading"}</span>}
        {engaged ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-loss" aria-hidden /> : null}
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={engaged ? "Release the kill switch" : "Halt all trading for this organisation"}
        description={
          engaged
            ? "Trading resumes only after the reason is recorded in the audit trail."
            : "Every strategy order is refused immediately. Existing contracts stay open — close them deliberately."
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
  const pathname = usePathname();
  const isActive = useActive(pathname);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const notifications = useApi<NotificationsResponse>((signal) =>
    api("/notifications", { signal, query: { limit: 20 } }),
  );
  const unread = notifications.data?.unread_count ?? 0;
  const plan = entitlements?.plan_code ?? subscription?.plan_code ?? "free";

  React.useEffect(() => {
    setMobileOpen(false);
    setMenuOpen(false);
  }, [pathname]);

  const signOut = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-obsidian-950">
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-line-soft bg-obsidian-900/50 px-3 py-5 lg:flex">
          <Link href="/app" className="mb-6 px-2">
            <Wordmark />
          </Link>

          <div className="mb-4 rounded-lg border border-line-soft bg-obsidian-850/80 px-3 py-2.5">
            <div className="flex items-center justify-between">
              <span className="label">Plan</span>
              <Badge tone="info">{plan}</Badge>
            </div>
            <p className="mt-2 flex items-center gap-1.5 text-2xs text-paper-faint">
              <ShieldCheck className="h-3 w-3 text-emerald-400/80" aria-hidden />
              {platform?.live_trading_enabled ? "Execution gate open" : "Live execution disabled"}
            </p>
          </div>

          <nav className="space-y-0.5" aria-label="Primary workspace">
            {PRIMARY.map((item) => (
              <NavItem key={item.href} item={item} active={isActive(item.href)} unread={unread} />
            ))}
          </nav>

          <p className="mt-5 px-3 text-3xs uppercase tracking-label text-paper-faint/70">Account</p>
          <nav className="mt-2 space-y-0.5" aria-label="Account workspace">
            {SECONDARY.map((item) => (
              <NavItem key={item.href} item={item} active={isActive(item.href)} unread={unread} />
            ))}
          </nav>

          <div className="mt-auto space-y-2 pt-4">
            {user?.is_staff ? (
              <Link
                href="/admin"
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-electric-300 transition hover:bg-obsidian-800"
              >
                <Gauge className="h-4 w-4" aria-hidden />
                Admin command centre
              </Link>
            ) : null}
            <KillSwitchControl />
            <p className="px-2 text-3xs leading-relaxed text-paper-faint/70">
              VELTRANE never holds your funds. Simulated results are not predictions.
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-line-soft bg-obsidian-950/85 px-3 backdrop-blur-xl sm:px-5">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                className="rounded-md p-1.5 text-paper-muted transition hover:bg-obsidian-800 lg:hidden"
                aria-label="Open navigation"
              >
                <Menu className="h-5 w-5" />
              </button>
              <Link href="/app" className="lg:hidden" aria-label="VELTRANE home">
                <Wordmark compact />
              </Link>
              <Link
                href="/app/markets"
                className="hidden items-center gap-2 rounded-lg border border-line-soft bg-obsidian-900/60 px-3 py-1.5 text-2xs text-paper-faint transition hover:border-line-strong hover:text-paper-muted md:flex"
              >
                <Search className="h-3.5 w-3.5" aria-hidden />
                Search markets
                <span className="kbd ml-6">⌘K</span>
              </Link>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="hidden items-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/[0.08] px-2.5 py-1 text-3xs uppercase tracking-label text-emerald-300 sm:flex">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
                Paper mode
              </span>
              <div className="lg:hidden">
                <KillSwitchControl compact />
              </div>
              <Link
                href="/app/notifications"
                className="relative rounded-md p-2 text-paper-muted transition hover:bg-obsidian-800 hover:text-paper"
                aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
              >
                <Bell className="h-4 w-4" />
                {unread > 0 ? (
                  <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-electric-400" />
                ) : null}
              </Link>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setMenuOpen((open) => !open)}
                  aria-expanded={menuOpen}
                  className="flex items-center gap-2 rounded-lg border border-line-soft px-1.5 py-1.5 text-xs text-paper-muted transition hover:border-line-strong hover:text-paper"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-md bg-obsidian-750 text-2xs text-paper">
                    {initials(user?.full_name ?? "V")}
                  </span>
                  <span className="hidden max-w-[9rem] truncate sm:block">{user?.full_name}</span>
                  <ChevronDown className="hidden h-3 w-3 sm:block" aria-hidden />
                </button>
                {menuOpen ? (
                  <div
                    className="absolute right-0 top-11 z-40 w-60 rounded-xl border border-line-strong bg-obsidian-850 p-1 shadow-lift"
                    onMouseLeave={() => setMenuOpen(false)}
                  >
                    <div className="px-3 py-2.5">
                      <p className="truncate text-xs text-paper">{user?.full_name}</p>
                      <p className="truncate text-2xs text-paper-faint">{user?.email}</p>
                      <div className="mt-2 flex items-center gap-1.5">
                        <Badge tone="info">{plan}</Badge>
                        {user?.mfa_enabled ? <Badge tone="gain">MFA</Badge> : <Badge tone="warn">No MFA</Badge>}
                      </div>
                    </div>
                    <div className="my-1 h-px bg-line-soft" />
                    {[
                      ["Account settings", "/app/settings"],
                      ["Billing & plan", "/app/billing"],
                      ["Connected accounts", "/app/accounts"],
                    ].map(([label, href]) => (
                      <Link
                        key={href}
                        href={href as Parameters<typeof Link>[0]["href"]}
                        className="block rounded-md px-3 py-2 text-xs text-paper-muted hover:bg-obsidian-800"
                      >
                        {label}
                      </Link>
                    ))}
                    {user?.is_staff ? (
                      <Link href="/admin" className="block rounded-md px-3 py-2 text-xs text-electric-300 hover:bg-obsidian-800">
                        Admin command centre
                      </Link>
                    ) : null}
                    <div className="my-1 h-px bg-line-soft" />
                    <button
                      type="button"
                      onClick={signOut}
                      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-paper-muted hover:bg-obsidian-800"
                    >
                      <LogOut className="h-3.5 w-3.5" aria-hidden />
                      Sign out
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          </header>

          <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-3 pb-24 pt-4 sm:px-5 lg:pb-8 lg:pt-6">
            {children}
          </main>
        </div>
      </div>

      {/* Mobile navigation */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-obsidian-950/85 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="relative flex h-full w-[280px] flex-col border-r border-line-strong bg-obsidian-900 px-3 py-5">
            <div className="mb-6 flex items-center justify-between px-2">
              <Wordmark />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="rounded-md p-1.5 text-paper-faint hover:bg-obsidian-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="space-y-0.5" aria-label="Mobile primary">
              {PRIMARY.map((item) => (
                <NavItem
                  key={item.href}
                  item={item}
                  active={isActive(item.href)}
                  unread={unread}
                  onNavigate={() => setMobileOpen(false)}
                />
              ))}
            </nav>
            <p className="mt-5 px-3 text-3xs uppercase tracking-label text-paper-faint/70">Account</p>
            <nav className="mt-2 space-y-0.5" aria-label="Mobile account">
              {SECONDARY.map((item) => (
                <NavItem
                  key={item.href}
                  item={item}
                  active={isActive(item.href)}
                  unread={unread}
                  onNavigate={() => setMobileOpen(false)}
                />
              ))}
            </nav>
            <div className="mt-auto space-y-2 pt-4">
              {user?.is_staff ? (
                <Link
                  href="/admin"
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-electric-300 hover:bg-obsidian-800"
                >
                  <Gauge className="h-4 w-4" aria-hidden />
                  Admin command centre
                </Link>
              ) : null}
              <KillSwitchControl />
              <button
                type="button"
                onClick={signOut}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-paper-muted hover:bg-obsidian-800"
              >
                <LogOut className="h-4 w-4" aria-hidden />
                Sign out
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Mobile bottom tabs */}
      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line-soft bg-obsidian-900/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
        aria-label="Bottom navigation"
      >
        <div className="mx-auto grid max-w-md grid-cols-5">
          {MOBILE_TABS.map((tab) => {
            const active = isActive(tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex flex-col items-center gap-1 py-2.5 text-3xs transition-colors",
                  active ? "text-electric-300" : "text-paper-faint",
                )}
              >
                <span
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-lg",
                    tab.accent && !active ? "cta-gold" : "",
                    active && !tab.accent ? "bg-electric-500/15" : "",
                  )}
                >
                  <tab.icon className="h-4 w-4" aria-hidden />
                </span>
                {tab.label}
              </Link>
            );
          })}
        </div>
      </nav>

      <div className="hidden" aria-hidden>
        <BrandMark />
      </div>
    </div>
  );
}
