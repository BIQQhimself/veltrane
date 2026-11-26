"use client";

import * as React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/hooks";
import { bps, dateTime, money, percent, signedMoney } from "@/lib/format";
import { contractReturn, contractStake } from "@/lib/contracts";
import { Donut } from "@/components/charts";
import { Badge, DemoBadge, StatusBadge } from "@/components/ui/badge";
import { EmptyState, ErrorNote, KeyValue, Skeleton, Stat } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { TradeDetailDialog } from "@/components/app/trade-detail";
import type { PortfolioOverview, Trade } from "@/lib/types";

type Performance = {
  stats: {
    trades: number;
    win_rate_pct: number;
    profit_factor: number | null;
    avg_win: number;
    avg_loss: number;
    net_pnl: number;
    fees: number;
    max_drawdown_pct: number;
  };
  trade_counts: { paper: number; demo: number; live: number };
  by_scope: Record<Scope, PeriodStats>;
  note: string;
};

type Scope = "paper" | "demo" | "live";

type PeriodStats = {
  trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  avg_win: number;
  avg_loss: number;
  net_pnl: number;
  fees: number;
};

const ALLOC_COLORS = ["#c8a96a", "#6a9bd8", "#3fb27f", "#c6cedb", "#a8894f", "#e0606f", "#7f8fa6"];

export default function PortfolioPage() {
  const [selectedTrade, setSelectedTrade] = React.useState<string | null>(null);
  const overview = useApi<PortfolioOverview>((signal) => api("/portfolio/overview", { signal }));
  const performance = useApi<Performance>((signal) => api("/portfolio/performance", { signal }));
  const trades = useApi<{ trades: Trade[] }>((signal) => api("/trades", { signal, query: { limit: 100 } }));

  const equity = overview.data?.equity;
  const allocation = (overview.data?.allocation ?? []).filter((slice) => slice.value > 0).slice(0, 7);
  const totalAllocation = allocation.reduce((sum, slice) => sum + slice.value, 0);
  // The donut describes the whole account, so unallocated cash is a slice of its
  // own. Showing "100% ETH" next to $29k of equity was actively misleading.
  const accountValue = Math.max(equity?.simulated_balance_usd ?? 0, totalAllocation);
  const cashValue = Math.max(0, accountValue - totalAllocation);
  const donutSlices = cashValue > 0 ? [...allocation, { label: "Cash (unallocated)", value: cashValue }] : allocation;
  const donutTotal = donutSlices.reduce((sum, slice) => sum + slice.value, 0) || 1;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Exposure"
        title="Portfolio"
        description="Live balances, simulated balances and paper equity are reported separately on purpose. They are never blended into one flattering number."
      />

      {overview.error ? <ErrorNote message={overview.error} onRetry={overview.refetch} /> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {overview.loading || !equity ? (
          <>
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
          </>
        ) : (
          <>
            <Stat label="Live balance" value={money(equity.live_balance_usd)} hint="from read-only syncs" />
            <Stat
              label="Simulated"
              value={money(equity.simulated_balance_usd)}
              hint={equity.simulated_source === "paper_session" ? "running paper session equity" : "simulated venue balances"}
            />
            <Stat
              label="Realised (net)"
              value={signedMoney(equity.realized_pnl_net)}
              tone={equity.realized_pnl_net >= 0 ? "gain" : "loss"}
              hint={`fees ${money(equity.fees_paid, "USD", 2)}`}
            />
            <Stat
              label="Open positions"
              value={`${overview.data?.positions.length ?? 0}`}
              hint="across all connections"
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1fr_1.3fr]">
        <Panel>
          <PanelHeader title="Allocation" subtitle="Balances and open position value" />
          <PanelBody>
            {overview.loading ? (
              <Skeleton className="h-44 w-full" />
            ) : donutSlices.length ? (
              <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:justify-between">
                <Donut
                  segments={donutSlices.map((slice, index) => ({
                    label: slice.label,
                    value: slice.value,
                    color: slice.label.startsWith("Cash")
                      ? "#44525f"
                      : ALLOC_COLORS[index % ALLOC_COLORS.length]!,
                  }))}
                  centerValue={percent((totalAllocation / donutTotal) * 100, 1)}
                  centerLabel="deployed"
                />
                <ul className="w-full space-y-2 sm:max-w-[190px]">
                  {donutSlices.map((slice, index) => (
                    <li key={slice.label} className="flex items-center justify-between gap-2 text-xs">
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{
                            backgroundColor: slice.label.startsWith("Cash")
                              ? "#44525f"
                              : ALLOC_COLORS[index % ALLOC_COLORS.length],
                          }}
                        />
                        <span className="truncate text-paper-muted">{slice.label}</span>
                      </span>
                      <span className="num text-paper">
                        {percent((slice.value / donutTotal) * 100, 1)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <EmptyState
                title="Nothing allocated yet"
                description="Allocation fills in as soon as a paper position is open or a read-only connection reports balances."
                action={
                  <div className="flex flex-wrap items-center justify-center gap-2">
                    <Link
                      href="/app/terminal"
                      className="rounded-lg border border-gold-400/40 bg-gold-400/10 px-3 py-1.5 text-xs text-gold-300 transition hover:border-gold-300 hover:bg-gold-400/15"
                    >
                      Open a paper position
                    </Link>
                    <Link
                      href="/app/accounts"
                      className="rounded-lg border border-line px-3 py-1.5 text-xs text-paper-muted transition hover:border-line-strong hover:text-paper"
                    >
                      Connect an account
                    </Link>
                  </div>
                }
              />
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Performance" subtitle="Closed trades only, net of recorded costs" />
          <PanelBody>
            {performance.loading ? (
              <Skeleton className="h-44 w-full" />
            ) : performance.data ? (
              <div className="space-y-4">
                <KeyValue
                  items={[
                    { label: "Trades closed", value: `${performance.data.stats.trades}`, mono: true },
                    { label: "Win rate", value: percent(performance.data.stats.win_rate_pct), mono: true },
                    { label: "Profit factor", value: performance.data.stats.profit_factor ?? "—", mono: true },
                    { label: "Average win", value: signedMoney(performance.data.stats.avg_win), mono: true },
                    { label: "Average loss", value: signedMoney(performance.data.stats.avg_loss), mono: true },
                    { label: "Max drawdown", value: percent(performance.data.stats.max_drawdown_pct), mono: true },
                    { label: "Net P&L", value: signedMoney(performance.data.stats.net_pnl), mono: true },
                  ]}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="info">paper {performance.data.trade_counts.paper}</Badge>
                  <Badge tone="neutral">demo {performance.data.trade_counts.demo}</Badge>
                  <Badge tone={performance.data.trade_counts.live ? "warn" : "neutral"}>
                    live {performance.data.trade_counts.live}
                  </Badge>
                </div>
                <dl className="grid grid-cols-3 gap-2 rounded-lg border border-line-soft bg-obsidian-900/40 px-3 py-2 text-2xs">
                  {(["paper", "demo", "live"] as const).map((scope) => {
                    const scopedNet = performance.data?.by_scope[scope]?.net_pnl;
                    return (
                    <div key={scope}>
                      <dt className="text-3xs uppercase tracking-label text-paper-faint">{scope} net</dt>
                      <dd
                        className={cn(
                          "num mt-0.5",
                          scopedNet === 0
                            ? "text-paper-muted"
                            : (scopedNet ?? 0) > 0
                              ? "text-gain"
                              : "text-loss",
                        )}
                      >
                        {signedMoney(scopedNet ?? 0)}
                      </dd>
                    </div>
                    );
                  })}
                </dl>
                <p className="text-2xs leading-relaxed text-paper-faint">{performance.data.note}</p>
              </div>
            ) : null}
          </PanelBody>
        </Panel>
      </div>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Balances" subtitle="As reported by each venue" />
          {overview.loading ? (
            <div className="p-5">
              <Skeleton className="h-24 w-full" />
            </div>
          ) : overview.data && overview.data.balances.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>Asset</TH>
                  <TH align="right">Free</TH>
                  <TH align="right">Locked</TH>
                  <TH align="right">USD value</TH>
                  <TH>As of</TH>
                </TR>
              </THead>
              <TBody>
                {overview.data.balances.map((balance, index) => (
                  <TR key={`${balance.asset}-${index}`}>
                    <TD mono>{balance.asset}</TD>
                    <TD align="right" mono>
                      {balance.free}
                    </TD>
                    <TD align="right" mono>
                      {balance.locked}
                    </TD>
                    <TD align="right" mono>
                      {money(balance.usd_value)}
                    </TD>
                    <TD>{dateTime(balance.as_of)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState
              title="No balances synced"
              description="Balances appear after a read-only sync. VELTRANE never requests withdrawal permission."
              action={
                <Link
                  href="/app/accounts"
                  className="rounded-lg border border-line px-3 py-1.5 text-xs text-paper-muted transition hover:border-line-strong hover:text-paper"
                >
                  Manage connections
                </Link>
              }
            />
          )}
        </Panel>

        <Panel>
          <PanelHeader
            title="Open positions"
            subtitle="Marked against the latest quote"
            action={
              <span className="text-2xs text-paper-faint">
                {overview.data?.positions.length ?? 0} open
              </span>
            }
          />
          {overview.data && overview.data.positions.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>Instrument</TH>
                  <TH>Side</TH>
                  <TH align="right">Qty</TH>
                  <TH align="right">Entry</TH>
                  <TH align="right">Mark</TH>
                  <TH align="right">Unrealised</TH>
                </TR>
              </THead>
              <TBody>
                {overview.data.positions.map((position) => (
                  <TR key={position.id}>
                    <TD mono>{position.symbol}</TD>
                    <TD>{position.side}</TD>
                    <TD align="right" mono>
                      {position.quantity}
                    </TD>
                    <TD align="right" mono>
                      {money(position.avg_entry_price)}
                    </TD>
                    <TD align="right" mono>
                      {position.mark_price === null ? "—" : money(position.mark_price)}
                    </TD>
                    <TD align="right" mono>
                      <span className={position.unrealized_pnl >= 0 ? "text-gain" : "text-loss"}>
                        {signedMoney(position.unrealized_pnl)}
                      </span>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState
              title="No open positions"
              description="Simulated contracts and synced venue positions both appear here while they are live."
            />
          )}
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="Trade history"
          subtitle="Every row opens the immutable record. A fixed-odds contract shows its stake and its return."
          action={<span className="text-2xs text-paper-faint">{trades.data?.trades.length ?? 0} records</span>}
        />
        {trades.loading ? (
          <div className="p-5">
            <Skeleton className="h-32 w-full" />
          </div>
        ) : trades.data && trades.data.trades.length ? (
          <Table>
            <THead>
              <TR>
                <TH>Instrument</TH>
                <TH>Side</TH>
                <TH align="right">Qty</TH>
                <TH align="right">Entry / stake</TH>
                <TH align="right">Exit / return</TH>
                <TH align="right">Fees</TH>
                <TH align="right">Slippage</TH>
                <TH align="right">Net P&amp;L</TH>
                <TH>Closed</TH>
                <TH>Mode</TH>
              </TR>
            </THead>
            <TBody>
              {trades.data.trades.map((trade) => (
                <TR key={trade.id} onClick={() => setSelectedTrade(trade.id)}>
                  <TD mono>{trade.symbol}</TD>
                  <TD>{trade.side}</TD>
                  <TD align="right" mono>
                    {trade.quantity}
                  </TD>
                  <TD align="right" mono>
                    {contractStake(trade) !== null ? money(contractStake(trade)) : money(trade.entry_price)}
                  </TD>
                  <TD align="right" mono>
                    {contractStake(trade) !== null
                      ? money(contractReturn(trade)?.value ?? trade.exit_price)
                      : money(trade.exit_price)}
                  </TD>
                  <TD align="right" mono>
                    {money(trade.fees, "USD", 2)}
                  </TD>
                  <TD align="right" mono>
                    {bps(trade.slippage_actual_bps)}
                  </TD>
                  <TD align="right" mono>
                    <span className={trade.net_pnl >= 0 ? "text-gain" : "text-loss"}>
                      {signedMoney(trade.net_pnl)}
                    </span>
                  </TD>
                  <TD>{dateTime(trade.closed_at)}</TD>
                  <TD>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge status={trade.mode} />
                      {trade.is_demo ? <DemoBadge /> : null}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState title="No trades yet" description="Closed positions appear here with full cost attribution." />
        )}
      </Panel>

      <TradeDetailDialog tradeId={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
}
