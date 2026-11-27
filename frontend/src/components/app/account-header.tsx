"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowDownToLine, Bell, ChevronDown, Eye, EyeOff, LogOut, Settings, ShieldAlert, ShieldCheck, UserRound, Wallet } from "lucide-react";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { dateOnly, money } from "@/lib/format";
import { usePresence } from "@/lib/presence";
import { capLabel, tierFor } from "@/lib/membership";
import type { NotificationsResponse } from "@/lib/types";
import { TierBadge, IdentityAvatar } from "@/components/app/tier-badge";

type Equity = {
  equity: { live_balance_usd: number; simulated_balance_usd: number; total_usd: number };
};

const BALANCE_HIDDEN_KEY = "veltrane.balanceHidden";

function useHiddenBalance() {
  const [hidden, setHidden] = React.useState(false);

  React.useEffect(() => {
    try {
      setHidden(window.localStorage.getItem(BALANCE_HIDDEN_KEY) === "1");
    } catch {
      /* private mode: keep the balance visible for this session only */
    }
  }, []);

  const toggle = React.useCallback(() => {
    setHidden((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(BALANCE_HIDDEN_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return { hidden, toggle };
}

/**
 * The signed-in trader's identity cluster: avatar with the tier ring, display name, account id,
 * plan badge, balance and the two money actions. Balances are read-only mirrors of the venue.
 */
export function AccountHeader() {
  const { user, identity, entitlements, subscription, logout, platform } = useAuth();
  const { automation } = usePresence();
  const [menuOpen, setMenuOpen] = React.useState(false);
  const { hidden, toggle } = useHiddenBalance();

  const plan = entitlements?.plan_code ?? subscription?.plan_code ?? "free";
  const tier = tierFor(plan);
  const portfolio = useApi<Equity>((signal) => api("/portfolio/overview", { signal }));
  const notifications = useApi<NotificationsResponse>((signal) =>
    api("/notifications", { signal, query: { limit: 1 } }),
  );
  useInterval(() => portfolio.refetch(), 60_000);

  const unread = notifications.data?.unread_count ?? 0;
  const equity = portfolio.data?.equity;
  const hasLive = (equity?.live_balance_usd ?? 0) > 0;
  const balance = hasLive ? equity?.live_balance_usd ?? 0 : equity?.simulated_balance_usd ?? 0;

  const name = identity?.display_name ?? user?.full_name ?? "Trader";

  async function signOut() {
    await logout();
    // A full load, so the sign-in page arrives with its own metadata and no workspace state.
    window.location.assign("/login");
  }

  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {/* Balance: one pill, the number first. The eye toggle only hides it on screen; the value
          is fetched either way. */}
      <div className="flex items-center gap-1.5 rounded-full border border-line-soft bg-obsidian-700/50 py-1 pl-3 pr-1.5">
        <div className="leading-tight">
          <p className="hidden text-[9px] uppercase tracking-label text-paper-faint sm:block">
            {hasLive ? "Live" : "Simulated"}
          </p>
          <p className="num text-[13px] font-medium text-paper" aria-live="polite">
            {portfolio.loading ? "—" : hidden ? "••••••" : money(balance)}
          </p>
        </div>
        <button
          type="button"
          onClick={toggle}
          className="hidden rounded-full p-1 text-paper-faint transition hover:bg-obsidian-700/80 hover:text-paper-muted sm:inline-flex"
          aria-label={hidden ? "Show balance" : "Hide balance"}
          aria-pressed={hidden}
        >
          {hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>
      </div>

      <Link
        href="/app/wallet"
        className="cta-gold hidden h-9 items-center gap-1.5 rounded-full px-3.5 text-2xs font-semibold sm:inline-flex"
      >
        <ArrowDownToLine className="h-3.5 w-3.5" aria-hidden />
        Deposit
      </Link>

      <Link
        href="/app/notifications"
        className="relative rounded-full p-2 text-paper-muted transition hover:bg-obsidian-700/80 hover:text-paper"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 ? (
          <span className="absolute right-1 top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-champagne-400 px-1 text-[9px] font-semibold text-on-accent">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </Link>

      <div className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          className={cn(
            "flex items-center gap-2 rounded-full border border-line-soft bg-obsidian-700/50 py-1 pl-1 pr-2 transition hover:border-line-strong",
            menuOpen && "border-line-strong bg-obsidian-700/80",
          )}
        >
          <IdentityAvatar name={name} color={identity?.avatar_color} planCode={plan} size={30} />
          <span className="hidden min-w-0 text-left 2xl:block">
            <span className="block max-w-[7.5rem] truncate text-2xs font-medium leading-tight text-paper">{name}</span>
            <span className="block text-3xs leading-tight text-paper-faint">
              {tier.badge} {tier.label}
            </span>
          </span>
          <ChevronDown className={cn("hidden h-3 w-3 text-paper-faint transition 2xl:block", menuOpen && "rotate-180")} aria-hidden />
        </button>

        {menuOpen ? (
          <div
            role="menu"
            className="absolute right-0 top-[calc(100%+8px)] z-40 w-72 overflow-hidden rounded-2xl border border-line-strong bg-obsidian-850 shadow-lift"
          >
            <div className="border-b border-line-soft bg-obsidian-800/60 px-4 py-3">
              <div className="flex items-center gap-3">
                <IdentityAvatar name={name} color={identity?.avatar_color} planCode={plan} size={38} />
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-paper">{name}</p>
                  <p className="truncate text-2xs text-paper-faint">{user?.email}</p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <TierBadge planCode={plan} size="xs" />
                {user?.mfa_enabled ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-gain/30 bg-gain/10 px-1.5 py-0.5 text-3xs uppercase tracking-label text-gain">
                    <ShieldCheck className="h-2.5 w-2.5" aria-hidden /> MFA
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-warn/30 bg-warn/10 px-1.5 py-0.5 text-3xs uppercase tracking-label text-warn">
                    <ShieldAlert className="h-2.5 w-2.5" aria-hidden /> No MFA
                  </span>
                )}
                <span className="text-3xs text-paper-faint">{capLabel(tier, automation?.used_today)}</span>
              </div>
            </div>

            <div className="px-1 py-1">
              {[
                { label: "Profile & identity", href: "/app/profile", icon: UserRound },
                { label: "Membership", href: "/app/membership", icon: tier.badge },
                { label: "Wallet", href: "/app/wallet", icon: Wallet },
                { label: "Settings", href: "/app/settings", icon: Settings },
              ].map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs text-paper-muted transition hover:bg-obsidian-800 hover:text-paper"
                >
                  {typeof item.icon === "string" ? (
                    <span aria-hidden className="w-3.5 text-center text-[11px]">
                      {item.icon}
                    </span>
                  ) : (
                    <item.icon className="h-3.5 w-3.5" aria-hidden />
                  )}
                  {item.label}
                </Link>
              ))}
              {user?.is_staff ? (
                <Link
                  href="/admin"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs text-champagne-600 transition hover:bg-obsidian-800"
                >
                  <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
                  Admin command centre
                </Link>
              ) : null}
            </div>

            <div className="border-t border-line-soft px-4 py-2.5 text-3xs text-paper-faint">
              <p>
                Live execution:{" "}
                <span className={platform?.live_trading_enabled ? "text-warn" : "text-paper-muted"}>
                  {platform?.live_trading_enabled ? "gate open" : "disabled"}
                </span>
              </p>
              <p className="mt-0.5">Member since {dateOnly(user?.created_at)}</p>
            </div>

            <button
              type="button"
              role="menuitem"
              onClick={signOut}
              className="flex w-full items-center gap-2.5 border-t border-line-soft px-4 py-2.5 text-left text-xs text-paper-muted transition hover:bg-obsidian-800 hover:text-paper"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden />
              Sign out
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
