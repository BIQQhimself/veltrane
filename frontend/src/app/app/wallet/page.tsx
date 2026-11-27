"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowDownToLine, ArrowUpFromLine, ExternalLink, Info, RefreshCw, Wallet as WalletIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateTime, money, number, titleCase } from "@/lib/format";
import { Badge, DemoBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { WalletResponse } from "@/lib/types";
import { cn } from "@/lib/cn";

export default function WalletPage() {
  const wallet = useApi<WalletResponse>((signal) => api("/wallet", { signal }));

  const totals = wallet.data?.totals;
  const accounts = wallet.data?.accounts ?? [];
  const transactions = wallet.data?.transactions ?? [];
  const funding = wallet.data?.funding;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Wallet"
        title="Balances and cash movements"
        description="VELTRANE never holds client money. These figures are mirrored from the exchange or broker you connected, and the ledger below lists the cash movements that sync produced."
        action={
          <Button variant="ghost" onClick={wallet.refetch} loading={wallet.loading}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
            Refresh
          </Button>
        }
      />

      {wallet.error ? <ErrorNote message={wallet.error} onRetry={wallet.refetch} /> : null}

      {wallet.loading && !wallet.data ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="tile tile-sheen p-4">
            <p className="metric-label">Live balance</p>
            <p className="metric mt-2">{money(totals?.live_usd ?? 0)}</p>
            <p className="mt-2 text-3xs text-paper-faint">Real funds at your venue. VELTRANE cannot move them.</p>
          </div>
          <div className="tile tile-sheen p-4">
            <p className="metric-label">Simulated balance</p>
            <p className="metric mt-2 text-info">{money(totals?.demo_usd ?? 0)}</p>
            <p className="mt-2 text-3xs text-paper-faint">Demo and paper money. Never counted as profit.</p>
          </div>
          <div className="tile tile-sheen p-4">
            <p className="metric-label">Paper session equity</p>
            <p className="metric mt-2">
              {totals?.paper_equity_usd === null || totals?.paper_equity_usd === undefined
                ? "—"
                : money(totals.paper_equity_usd)}
            </p>
            <Link href="/app/terminal" className="mt-2 inline-block text-3xs text-champagne-600 hover:text-champagne-600">
              Open the terminal →
            </Link>
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <section className="tile" aria-label="Connected accounts and balances">
          <div className="panel-header">
            <h2 className="text-sm font-medium text-paper">Accounts</h2>
            <Link href="/app/accounts" className="text-2xs text-champagne-600 hover:text-champagne-600">
              Manage connections →
            </Link>
          </div>
          {accounts.length === 0 ? (
            <div className="p-5">
              <EmptyState
                title="No account connected yet"
                description="Connect a Deriv or crypto exchange account to see balances here. Read-only access is enough to start."
                action={
                  <Link href="/app/accounts" className="cta-gold rounded-lg px-3 py-2 text-2xs font-medium">
                    Connect an account
                  </Link>
                }
              />
            </div>
          ) : (
            <ul className="divide-y divide-line-soft">
              {accounts.map((account) => (
                <li key={account.connection_id} className="px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-xs font-medium text-paper">{account.label}</p>
                        <StatusBadge status={account.status} />
                        {account.is_simulated ? <DemoBadge /> : <Badge tone="outline">{account.environment}</Badge>}
                      </div>
                      <p className="mt-1 text-2xs text-paper-faint">
                        {titleCase(account.provider)} · {account.account_id ?? "account id pending"} ·{" "}
                        {account.stale ? "never synced" : `synced ${dateTime(account.last_sync_at)}`}
                      </p>
                    </div>
                    <p className={cn("num text-sm", account.is_simulated ? "text-info" : "text-paper")}>
                      {money(account.balance_usd, account.currency)}
                    </p>
                  </div>
                  {account.assets.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {account.assets.slice(0, 6).map((asset) => (
                        <span
                          key={asset.asset}
                          className="rounded-full border border-line-soft bg-obsidian-900/70 px-2 py-0.5 text-3xs text-paper-muted"
                        >
                          <span className="num">{number(asset.total, 4)}</span> {asset.asset}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="tile p-5" aria-label="Funding">
          <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
            <WalletIcon className="h-4 w-4 text-gold-600" aria-hidden />
            Deposits and withdrawals
          </h2>
          <p className="mt-2 text-2xs leading-relaxed text-paper-muted">{funding?.note}</p>
          <div className="mt-4 grid gap-2">
            <Link
              href="/app/accounts"
              className="cta-gold inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-2xs font-medium"
            >
              <ArrowDownToLine className="h-3.5 w-3.5" aria-hidden />
              Fund at your provider
            </Link>
            <Link
              href="/app/accounts"
              id="withdraw"
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-line-strong px-3 py-2 text-2xs text-paper-muted transition hover:bg-obsidian-800 hover:text-paper"
            >
              <ArrowUpFromLine className="h-3.5 w-3.5" aria-hidden />
              Withdraw at your provider
            </Link>
          </div>
          <p className="mt-4 flex gap-2 rounded-lg border border-line-soft bg-obsidian-900/60 p-3 text-3xs leading-relaxed text-paper-faint">
            <Info className="mt-0.5 h-3 w-3 shrink-0 text-champagne-600" aria-hidden />
            We ask for trading permission only and never request withdrawal access, so VELTRANE cannot withdraw on
            your behalf even if a token were compromised.
          </p>
          {(funding?.providers ?? []).length > 0 ? (
            <p className="mt-3 text-3xs text-paper-faint">
              Providers: {(funding?.providers ?? []).map(titleCase).join(", ")}
            </p>
          ) : null}
        </section>
      </div>

      <section className="tile" aria-label="Cash movements">
        <div className="panel-header">
          <div>
            <h2 className="text-sm font-medium text-paper">Cash movements</h2>
            <p className="mt-0.5 text-2xs text-paper-faint">
              Deposits, withdrawals, fees and funding recorded by account sync.
            </p>
          </div>
          <Badge tone="neutral">{transactions.length} entries</Badge>
        </div>
        {transactions.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title="No cash movements yet"
              description="Once an account is synced, deposits, withdrawals and funding charges appear here."
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>When</TH>
                <TH>Type</TH>
                <TH>Account</TH>
                <TH className="text-right">Amount</TH>
                <TH className="text-right">Fee</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {transactions.map((entry) => (
                <TR key={entry.id}>
                  <TD className="whitespace-nowrap text-2xs text-paper-faint">{dateTime(entry.occurred_at)}</TD>
                  <TD>
                    <span className="text-xs text-paper">{titleCase(entry.type)}</span>
                  </TD>
                  <TD className="text-2xs text-paper-muted">{entry.connection_label ?? "—"}</TD>
                  <TD className="num text-right text-xs text-paper">
                    {money(entry.amount)} <span className="text-2xs text-paper-faint">{entry.asset}</span>
                  </TD>
                  <TD className="num text-right text-2xs text-paper-faint">{entry.fee ? money(entry.fee) : "—"}</TD>
                  <TD className="text-right">
                    {entry.simulated ? (
                      <DemoBadge />
                    ) : entry.reference_id ? (
                      <span className="inline-flex items-center gap-1 text-3xs text-paper-faint">
                        <ExternalLink className="h-3 w-3" aria-hidden />
                        {entry.reference_type ?? "ref"}
                      </span>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </section>
    </div>
  );
}
