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
  Gift,
  GraduationCap,
  LayoutDashboard,
  LifeBuoy,
  LineChart,
  LogOut,
  Menu,
  Plug,
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
import { automationSummary, tierFor } from "@/lib/membership";
import { Wordmark } from "@/components/brand";
import { AccountHeader } from "@/components/app/account-header";
import { KillSwitchControl } from "@/components/app/kill-switch";
import type { NotificationsResponse } from "@/lib/types";

type NavEntry = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
};

/** The seven destinations that deserve a permanent slot in the top rail. */
const PRIMARY: NavEntry[] = [
  { href: "/app", label: "Overview", icon: LayoutDashboard },
  { href: "/app/terminal", label: "Trade", icon: Activity },
  { href: "/app/markets", label: "Markets", icon: LineChart },
  { href: "/app/strategies", label: "Strategies", icon: Sparkles },
  { href: "/app/copilot", label: "Copilot", icon: Bot },
  { href: "/app/portfolio", label: "Portfolio", icon: BarChart3 },
  { href: "/app/wallet", label: "Wallet", icon: Wallet },
];

const MORE: NavEntry[] = [
  { href: "/app/analytics", label: "Analytics", icon: Gauge },
  { href: "/app/accounts", label: "Connected accounts", icon: Plug },
  { href: "/app/membership", label: "Membership", icon: CreditCard },
  { href: "/app/referrals", label: "Referrals", icon: Users },
  { href: "/app/promotions", label: "Promotions", icon: Gift },
  { href: "/app/education", label: "Education", icon: GraduationCap },
];

const UTILITY: NavEntry[] = [
  { href: "/app/notifications", label: "Notifications", icon: Bell },
  { href: "/app/support", label: "Support", icon: LifeBuoy },
  { href: "/app/billing", label: "Billing", icon: CreditCard },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

/** Mobile gets five slots. "Trade" is the one that earns the centre, gold, raised position. */
const MOBILE_TABS: NavEntry[] = [
  { href: "/app", label: "Home", icon: LayoutDashboard },
  { href: "/app/markets", label: "Markets", icon: LineChart },
  { href: "/app/terminal", label: "Trade", icon: Activity },
  { href: "/app/portfolio", label: "Portfolio", icon: BarChart3 },
];

function useActive(pathname: string) {
  return React.useCallback(
    (href: string) => (href === "/app" ? pathname === "/app" : pathname.startsWith(href)),
    [pathname],
  );
}

function useDismiss(open: boolean, close: () => void) {
  const ref = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
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
        "hidden items-center gap-2 whitespace-nowrap rounded-full border px-2.5 py-1.5 text-3xs transition 2xl:flex",
        summary.tone === "gain"
          ? "border-gain/25 bg-gain/[0.07] text-gain hover:bg-gain/[0.12]"
          : summary.tone === "warn"
            ? "border-warn/25 bg-warn/[0.07] text-warn hover:bg-warn/[0.12]"
            : "border-line-soft bg-obsidian-700/50 text-paper-muted",
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
      {summary.title}
    </Link>
  );
}

function MoreMenu({ isActive }: { isActive: (href: string) => boolean }) {
  const [open, setOpen] = React.useState(false);
  const close = React.useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);
  const pathname = usePathname();

  React.useEffect(() => {
    setOpen(false);
  }, [pathname]);

  const active = [...MORE, ...UTILITY].some((item) => isActive(item.href));

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        data-active={active}
        className="nav-link"
      >
        More
        <ChevronDown className={cn("h-3.5 w-3.5 transition", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute left-0 top-[calc(100%+10px)] z-40 w-64 overflow-hidden rounded-2xl border border-line-strong bg-obsidian-850/95 p-1.5 shadow-lift backdrop-blur-xl"
        >
          {MORE.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              role="menuitem"
              className={cn(
                "flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition",
                isActive(item.href) ? "bg-obsidian-700/80 text-paper" : "text-paper-muted hover:bg-obsidian-700/60 hover:text-paper",
              )}
            >
              <item.icon className="h-4 w-4 opacity-80" aria-hidden />
              {item.label}
            </Link>
          ))}
          <div className="my-1.5 h-px bg-line-soft" />
          {UTILITY.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              role="menuitem"
              className={cn(
                "flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition",
                isActive(item.href) ? "bg-obsidian-700/80 text-paper" : "text-paper-muted hover:bg-obsidian-700/60 hover:text-paper",
              )}
            >
              <item.icon className="h-4 w-4 opacity-80" aria-hidden />
              {item.label}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SheetLink({
  item,
  active,
  onNavigate,
  badge,
}: {
  item: NavEntry;
  active: boolean;
  onNavigate: () => void;
  badge?: React.ReactNode;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition",
        active ? "bg-obsidian-700/85 text-paper" : "text-paper-muted hover:bg-obsidian-700/60 hover:text-paper",
      )}
    >
      <item.icon className={cn("h-4 w-4", active ? "text-champagne-600" : "opacity-70")} aria-hidden />
      <span className="flex-1 truncate">{item.label}</span>
      {badge}
    </Link>
  );
}

function SheetContent({ onNavigate }: { onNavigate: () => void }) {
  const pathname = usePathname();
  const isActive = useActive(pathname);
  const { user, logout } = useAuth();
  const router = useRouter();
  const notifications = useApi<NotificationsResponse>((signal) =>
    api("/notifications", { signal, query: { limit: 1 } }),
  );
  const unread = notifications.data?.unread_count ?? 0;

  const unreadBadge = unread ? (
    <span className="rounded-full bg-champagne-500/20 px-1.5 text-3xs text-champagne-600">{unread}</span>
  ) : undefined;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 pb-3 pt-4">
        <Wordmark compact />
        <button
          type="button"
          onClick={onNavigate}
          aria-label="Close navigation"
          className="rounded-full p-2 text-paper-faint transition hover:bg-obsidian-700/80 hover:text-paper"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 pb-4">
        <div>
          <p className="mb-1.5 px-3 text-3xs uppercase tracking-label text-paper-faint/60">Trading</p>
          <nav className="space-y-0.5" aria-label="Trading">
            {PRIMARY.map((item) => (
              <SheetLink key={item.href} item={item} active={isActive(item.href)} onNavigate={onNavigate} />
            ))}
          </nav>
        </div>
        <div>
          <p className="mb-1.5 px-3 text-3xs uppercase tracking-label text-paper-faint/60">Account</p>
          <nav className="space-y-0.5" aria-label="Account">
            {MORE.map((item) => (
              <SheetLink key={item.href} item={item} active={isActive(item.href)} onNavigate={onNavigate} />
            ))}
          </nav>
        </div>
        <div>
          <p className="mb-1.5 px-3 text-3xs uppercase tracking-label text-paper-faint/60">Support</p>
          <nav className="space-y-0.5" aria-label="Support">
            {UTILITY.map((item) => (
              <SheetLink
                key={item.href}
                item={item}
                active={isActive(item.href)}
                onNavigate={onNavigate}
                badge={item.href === "/app/notifications" ? unreadBadge : undefined}
              />
            ))}
          </nav>
        </div>
        {user?.is_staff ? (
          <Link
            href="/admin"
            onClick={onNavigate}
            className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] text-champagne-600 transition hover:bg-obsidian-700/60"
          >
            <Gauge className="h-4 w-4" aria-hidden />
            Admin command centre
          </Link>
        ) : null}
      </div>

      <div className="space-y-2 border-t border-line-soft p-3">
        <KillSwitchControl />
        <button
          type="button"
          onClick={async () => {
            await logout();
            router.push("/login");
          }}
          className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-xs text-paper-muted transition hover:bg-obsidian-700/60 hover:text-paper"
        >
          <LogOut className="h-4 w-4" aria-hidden />
          Sign out
        </button>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isActive = useActive(pathname);
  const [sheetOpen, setSheetOpen] = React.useState(false);

  React.useEffect(() => {
    setSheetOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    document.body.style.overflow = sheetOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [sheetOpen]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-line-soft bg-obsidian-950/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-[1560px] items-center gap-2 px-3 sm:gap-4 sm:px-6">
          <Link href="/app" className="flex shrink-0 items-center" aria-label="VELTRANE overview">
            <span className="hidden sm:block">
              <Wordmark />
            </span>
            <span className="sm:hidden">
              <Wordmark compact />
            </span>
          </Link>

          <nav className="ml-1 hidden items-center gap-0.5 xl:flex" aria-label="Primary">
            {PRIMARY.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(item.href) ? "page" : undefined}
                data-active={isActive(item.href)}
                className="nav-link"
              >
                {item.label}
              </Link>
            ))}
            <MoreMenu isActive={isActive} />
          </nav>

          <div className="ml-auto flex min-w-0 items-center gap-1.5 sm:gap-2.5">
            <AutomationPill />
            <KillSwitchControl iconOnly className="hidden lg:flex" />
            <AccountHeader />
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="rounded-full p-2 text-paper-muted transition hover:bg-obsidian-700/80 hover:text-paper xl:hidden"
              aria-label="Open navigation"
              aria-expanded={sheetOpen}
            >
              <Menu className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-[1560px] flex-1 px-3 pb-28 pt-5 sm:px-6 lg:pb-12">
        {children}
      </main>

      <footer className="hidden border-t border-line-soft px-6 py-5 text-3xs text-paper-faint lg:block">
        <div className="mx-auto flex max-w-[1560px] flex-wrap items-center justify-between gap-3">
          <p>VELTRANE never holds your funds. Simulated results are not predictions of future returns.</p>
          <div className="flex items-center gap-5">
            <Link href="/app/education" className="transition hover:text-paper-muted">
              Risk disclosure
            </Link>
            <Link href="/app/support" className="transition hover:text-paper-muted">
              Support
            </Link>
          </div>
        </div>
      </footer>

      {/* Mobile drawer: the full map of the product, with the kill switch where the thumb
          already is rather than buried in settings. */}
      {sheetOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-obsidian-950/85 backdrop-blur-sm"
            onClick={() => setSheetOpen(false)}
            aria-hidden
          />
          <div className="relative flex h-full w-[300px] max-w-[86vw] flex-col border-r border-line-strong bg-obsidian-900 shadow-lift">
            <SheetContent onNavigate={() => setSheetOpen(false)} />
          </div>
        </div>
      ) : null}

      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line-soft bg-obsidian-900/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
        aria-label="Bottom navigation"
      >
        <div className="mx-auto grid max-w-md grid-cols-5 items-end px-2">
          {MOBILE_TABS.map((tab) => {
            const active = isActive(tab.href);
            const isTrade = tab.href === "/app/terminal";
            if (isTrade) {
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className="flex flex-col items-center gap-1 pb-1.5 text-3xs text-paper-muted"
                >
                  <span
                    className={cn(
                      "-mt-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-champagne-600/40 bg-gradient-to-b from-champagne-300 to-champagne-500 text-on-accent shadow-[0_12px_24px_-12px_rgba(203,182,145,0.9)]",
                      active && "ring-2 ring-champagne-300/40",
                    )}
                  >
                    <tab.icon className="h-5 w-5" aria-hidden />
                  </span>
                  <span className={cn(active ? "text-paper" : "text-paper-faint")}>{tab.label}</span>
                </Link>
              );
            }
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex flex-col items-center gap-1 py-2.5 text-3xs transition-colors",
                  active ? "text-paper" : "text-paper-faint",
                )}
              >
                <tab.icon className={cn("h-5 w-5", active && "text-champagne-600")} aria-hidden />
                {tab.label}
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            className="flex flex-col items-center gap-1 py-2.5 text-3xs text-paper-faint"
            aria-label="More"
          >
            <Menu className="h-5 w-5" aria-hidden />
            More
          </button>
        </div>
      </nav>
    </div>
  );
}
