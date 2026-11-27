"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  CreditCard,
  Gauge,
  Gift,
  GraduationCap,
  LayoutDashboard,
  LifeBuoy,
  LineChart,
  LogOut,
  Menu,
  Plug,
  Search,
  Settings,
  Sparkles,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { usePresence } from "@/lib/presence";
import { automationSummary, capLabel, tierFor } from "@/lib/membership";
import { Wordmark } from "@/components/brand";
import { AccountHeader } from "@/components/app/account-header";
import { KillSwitchControl } from "@/components/app/kill-switch";
import { TierBadge } from "@/components/app/tier-badge";
import type { NotificationsResponse } from "@/lib/types";

type NavEntry = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
};

const GROUPS: { title: string; items: NavEntry[] }[] = [
  {
    title: "Trading",
    items: [
      { href: "/app", label: "Overview", icon: LayoutDashboard },
      { href: "/app/terminal", label: "Terminal", icon: Activity },
      { href: "/app/markets", label: "Markets", icon: LineChart },
      { href: "/app/strategies", label: "Strategies", icon: Sparkles },
      { href: "/app/copilot", label: "Copilot", icon: Bot },
    ],
  },
  {
    title: "Money",
    items: [
      { href: "/app/wallet", label: "Wallet", icon: Wallet },
      { href: "/app/portfolio", label: "Portfolio", icon: BarChart3 },
      { href: "/app/analytics", label: "Analytics", icon: Gauge },
    ],
  },
  {
    title: "Account",
    items: [
      { href: "/app/accounts", label: "Connected accounts", icon: Plug },
      { href: "/app/membership", label: "Membership", icon: CreditCard },
      { href: "/app/referrals", label: "Referrals", icon: Users },
      { href: "/app/promotions", label: "Promotions", icon: Gift },
      { href: "/app/education", label: "Education", icon: GraduationCap },
    ],
  },
];

const SUPPORT_LINKS: NavEntry[] = [
  { href: "/app/notifications", label: "Notifications", icon: Bell },
  { href: "/app/support", label: "Support", icon: LifeBuoy },
  { href: "/app/billing", label: "Billing", icon: CreditCard },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

const MOBILE_TABS: NavEntry[] = [
  { href: "/app", label: "Home", icon: LayoutDashboard },
  { href: "/app/markets", label: "Markets", icon: LineChart },
  { href: "/app/terminal", label: "Trade", icon: Activity },
  { href: "/app/wallet", label: "Wallet", icon: Wallet },
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
  badge,
  onNavigate,
}: {
  item: NavEntry;
  active: boolean;
  badge?: React.ReactNode;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-xs transition-colors",
        active
          ? "bg-gradient-to-r from-electric-500/15 to-transparent text-paper shadow-[inset_0_0_0_1px_rgba(46,123,255,0.22)]"
          : "text-paper-faint hover:bg-obsidian-800/70 hover:text-paper-muted",
      )}
    >
      {active ? (
        <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-electric-400" aria-hidden />
      ) : null}
      <item.icon className={cn("h-4 w-4", active ? "text-electric-300" : "text-paper-faint/75")} aria-hidden />
      <span className="flex-1 truncate">{item.label}</span>
      {badge}
    </Link>
  );
}

/** Session automation only stays alive while this tab beats, so the pill says which mode is live. */
function AutomationPill() {
  const { entitlements, subscription } = useAuth();
  const { automation } = usePresence();
  const tier = tierFor(entitlements?.plan_code ?? subscription?.plan_code);
  if (!automation || automation.mode === "none") return null;
  const summary = automationSummary(tier, automation);
  return (
    <Link
      href="/app/membership"
      className={cn(
        "flex items-center gap-2 rounded-full border px-2.5 py-1 text-3xs transition",
        summary.tone === "gain"
          ? "border-gain/30 bg-gain/[0.08] text-gain hover:bg-gain/15"
          : summary.tone === "warn"
            ? "border-warn/30 bg-warn/[0.08] text-warn hover:bg-warn/15"
            : "border-line-strong bg-obsidian-800 text-paper-muted",
      )}
      title={summary.detail}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          summary.tone === "gain" ? "animate-pulse bg-gain" : summary.tone === "warn" ? "bg-warn" : "bg-paper-faint",
        )}
        aria-hidden
      />
      <span className="hidden sm:inline">{summary.title}</span>
      <span className="sm:hidden" aria-hidden>
        {tier.badge}
      </span>
    </Link>
  );
}

function MembershipCard({ onNavigate }: { onNavigate?: () => void }) {
  const { entitlements, subscription } = useAuth();
  const { automation } = usePresence();
  const plan = entitlements?.plan_code ?? subscription?.plan_code ?? "free";
  const tier = tierFor(plan);
  return (
    <Link
      href="/app/membership"
      onClick={onNavigate}
      className="tile tier-glow block p-3 transition hover:border-line-strong"
      data-tier={tier.code}
    >
      <div className="flex items-center justify-between gap-2">
        <TierBadge planCode={plan} size="xs" />
        <span className="truncate text-3xs text-paper-faint">{tier.promise}</span>
      </div>
      <p className="mt-2 text-2xs leading-relaxed text-paper-muted">
        {automation ? capLabel(tier, automation.used_today) : capLabel(tier)}
      </p>
      <p className="mt-1 text-3xs text-electric-300">{plan === "elite" ? "Manage plan →" : "Upgrade →"}</p>
    </Link>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const isActive = useActive(pathname);
  const { user } = useAuth();
  const notifications = useApi<NotificationsResponse>((signal) =>
    api("/notifications", { signal, query: { limit: 1 } }),
  );
  const unread = notifications.data?.unread_count ?? 0;

  const unreadBadge = unread ? (
    <span className="rounded-full bg-electric-500/20 px-1.5 text-3xs text-electric-200">{unread}</span>
  ) : undefined;

  return (
    <>
      <Link href="/app" className="mb-5 block px-2" onClick={onNavigate}>
        <Wordmark />
      </Link>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-0.5">
        {GROUPS.map((group) => (
          <div key={group.title}>
            <p className="mb-1.5 px-3 text-3xs uppercase tracking-label text-paper-faint/60">{group.title}</p>
            <nav className="space-y-0.5" aria-label={group.title}>
              {group.items.map((item) => (
                <NavItem
                  key={item.href}
                  item={item}
                  active={isActive(item.href)}
                  onNavigate={onNavigate}
                  badge={item.href === "/app/notifications" ? unreadBadge : undefined}
                />
              ))}
            </nav>
          </div>
        ))}

        <div>
          <p className="mb-1.5 px-3 text-3xs uppercase tracking-label text-paper-faint/60">Support</p>
          <nav className="space-y-0.5" aria-label="Support">
            {SUPPORT_LINKS.map((item) => (
              <NavItem
                key={item.href}
                item={item}
                active={isActive(item.href)}
                onNavigate={onNavigate}
                badge={item.href === "/app/notifications" ? unreadBadge : undefined}
              />
            ))}
          </nav>
        </div>
      </div>

      <div className="mt-3 shrink-0 space-y-2 border-t border-line-soft pt-3">
        {user?.is_staff ? (
          <Link
            href="/admin"
            onClick={onNavigate}
            className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-electric-300 transition hover:bg-obsidian-800"
          >
            <Gauge className="h-4 w-4" aria-hidden />
            Admin command centre
          </Link>
        ) : null}
        <MembershipCard onNavigate={onNavigate} />
        <KillSwitchControl />
      </div>
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const isActive = useActive(pathname);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  React.useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const signOut = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-obsidian-950">
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-[244px] shrink-0 flex-col overflow-y-auto overscroll-contain border-r border-line-soft bg-obsidian-900/60 px-3 py-5 lg:flex">
          <SidebarContent />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-line-soft bg-obsidian-950/85 backdrop-blur-xl">
            <div className="flex h-16 items-center justify-between gap-3 px-3 sm:px-5">
              <div className="flex min-w-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => setMobileOpen(true)}
                  className="rounded-lg p-2 text-paper-muted transition hover:bg-obsidian-800 lg:hidden"
                  aria-label="Open navigation"
                >
                  <Menu className="h-5 w-5" />
                </button>
                <Link href="/app" className="lg:hidden" aria-label="VELTRANE home">
                  <Wordmark compact />
                </Link>
                <Link
                  href="/app/markets"
                  className="hidden items-center gap-2 rounded-xl border border-line-soft bg-obsidian-900/60 px-3 py-2 text-2xs text-paper-faint transition hover:border-line-strong hover:text-paper-muted md:flex"
                >
                  <Search className="h-3.5 w-3.5" aria-hidden />
                  Search markets, strategies
                  <span className="kbd ml-6">⌘K</span>
                </Link>
                <AutomationPill />
              </div>
              <AccountHeader />
            </div>
          </header>

          <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 px-3 pb-28 pt-4 sm:px-5 lg:pb-10 lg:pt-6">
            {children}
          </main>

          <footer className="hidden border-t border-line-soft px-5 py-4 text-3xs text-paper-faint lg:block">
            <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-2">
              <p>VELTRANE never holds your funds. Simulated results are not predictions of future returns.</p>
              <div className="flex items-center gap-4">
                <Link href="/app/education" className="transition hover:text-paper-muted">
                  Risk disclosure
                </Link>
                <Link href="/app/support" className="transition hover:text-paper-muted">
                  Support
                </Link>
              </div>
            </div>
          </footer>
        </div>
      </div>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-obsidian-950/85 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="relative flex h-full w-[286px] flex-col border-r border-line-strong bg-obsidian-900 px-3 py-5">
            <div className="mb-4 flex items-center justify-end">
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="rounded-md p-1.5 text-paper-faint hover:bg-obsidian-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
            <button
              type="button"
              onClick={signOut}
              className="mt-2 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-xs text-paper-muted hover:bg-obsidian-800"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out
            </button>
          </div>
        </div>
      ) : null}

      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line-soft bg-obsidian-900/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
        aria-label="Bottom navigation"
      >
        <div className="mx-auto grid max-w-md grid-cols-5">
          {MOBILE_TABS.map((tab) => {
            const active = isActive(tab.href);
            const isTrade = tab.href === "/app/terminal";
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
                    "flex h-8 w-8 items-center justify-center rounded-xl",
                    isTrade && !active ? "cta-gold" : "",
                    active && !isTrade ? "bg-electric-500/15" : "",
                    isTrade && active ? "bg-gold-500/20 text-gold-300" : "",
                  )}
                >
                  <tab.icon className="h-4 w-4" aria-hidden />
                </span>
                {tab.label}
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="flex flex-col items-center gap-1 py-2.5 text-3xs text-paper-faint"
            aria-label="More"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-xl">
              <Menu className="h-4 w-4" aria-hidden />
            </span>
            More
          </button>
        </div>
      </nav>
    </div>
  );
}
