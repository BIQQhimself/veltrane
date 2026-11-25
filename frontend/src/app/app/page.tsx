"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, CircleDollarSign, Gauge, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, money, percent, signedMoney, titleCase } from "@/lib/format";
import { AreaChart } from "@/components/charts";
import { Badge, DemoBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, Progress, Skeleton, Stat } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { TradeDetailDialog } from "@/components/app/trade-detail";
import type { PortfolioOverview, Trade, TradingState } from "@/lib/types";

type Performance = {
  curve: Array<{ date: string; pnl: number; cumulative: number }>;
  stats: {
    trades: number;
    win_rate_pct: number;
    profit_factor: number | null;
    net_pnl: number;
    max_drawdown_pct: number;
    paper_trades: number;
    live_trades: number;
  };
};

const ONBOARDING = [
  "Verify your email",
  "Secure the account with MFA",
  "Choose a plan",
  "Connect an account",
  "Sync read-only data",
  "Set your risk preferences",
  "Configure a strategy",
  "Start paper trading",
  "Review the risk policy",
  "Authorise live trading (eligible plans only)",
];

export default function OverviewPage() {
  const { user, organization, entitlements, subscription, usage, live, platform } = useAuth();
  const [selectedTrade, setSelectedTrade] = React.useState<string | null>(null);

  const portfolio = useApi<PortfolioOverview>((signal) => api("/portfolio/overview", { signal }));
  const performance = useApi<Performance>((signal) => api("/portfolio/performance", { signal }));
  const state = useApi<TradingState>((signal) => api("/trading/state", { signal }));
  const trades = useApi<{ trades: Trade[] }>((signal) => api("/trades", { signal, query: { limit: 8 } }));

  const equity = portfolio.data?.equity;
  const curve = performance.data?.curve ?? [];
  const cumulative = curve.map((point) => point.cumulative);
  const step = Math.max(
    user?.onboarding_step ?? 0,
    user?.email_verified ? 1 : 0,
    user?.mfa_enabled ? 2 : 0,
    subscription && subscription.plan_code !== "free" ? 3 : 0,
  );
  const killEngaged = Boolean(
    (state.data?.kill_switches as Record<string, { engaged?: boolean }> | undefined)?.org?.engaged,
  );

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow={organization?.name ?? "Workspace"}
        title={`Good to see you, ${(user?.full_name ?? "trader").split(" ")[0]}`}
        description="Positions, risk posture and connection health in one place. Paper trading is always available; live execution is gated."
        action={
          <Link href="/app/terminal">
            <Button size="sm">
              Trading terminal
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        }
      />

      {step < 10 ? (
        <Panel className="border-champagne-600/30 bg-gradient-to-r from-champagne-500/[0.06] to-transparent">
          <PanelBody className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-champagne-400" aria-hidden />
                <p className="text-sm text-paper">Finish setting up your workspace</p>
                <Badge tone="gold">{step}/10</Badge>
              </div>
              <p className="mt-1 text-xs text-paper-faint">
                Next: {ONBOARDING[Math.min(step, 9)]}. Live trading stays locked until every prerequisite is met.
              </p>
              <div className="mt-3 max-w-sm">
                <Progress value={step} max={10} />
              </div>
            </div>
            <Link href="/app/onboarding">
              <Button variant="secondary" size="sm">
                Continue setup
              </Button>
            </Link>
          </PanelBody>
        </Panel>
      ) : null}

      {portfolio.error ? <ErrorNote message={portfolio.error} onRetry={portfolio.refetch} /> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {portfolio.loading || !equity ? (
          <>
            <Skeleton className="h-[124px]" />
            <Skeleton className="h-[124px]" />
            <Skeleton className="h-[124px]" />
            <Skeleton className="h-[124px]" />
          </>
        ) : (
          <>
            <Stat
              label="Total equity"
              value={money(equity.total_usd)}
              hint={equity.simulated_balance_usd > 0 ? "includes simulated balances" : undefined}
            />
            <Stat
              label="Unrealised P&L"
              value={signedMoney(equity.unrealized_pnl)}
              tone={equity.unrealized_pnl >= 0 ? "gain" : "loss"}
              hint="open positions, marked"
            />
            <Stat
              label="Realised P&L (net)"
              value={signedMoney(equity.realized_pnl_net)}
              tone={equity.realized_pnl_net >= 0 ? "gain" : "loss"}
              hint={`after ${money(equity.fees_paid, "USD", 2)} fees`}
            />
            <Stat
              label="Demo executions today"
              value={`${state.data?.demo_executions_today ?? usage?.demo_executions_today ?? 0}`}
              hint={
                typeof entitlements?.limits?.max_daily_demo_executions === "number"
                  ? `limit ${entitlements.limits.max_daily_demo_executions}`
                  : "unlimited on your plan"
              }
            />
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.55fr_1fr]">
        <Panel>
          <PanelHeader
            title="Cumulative net P&L"
            subtitle="Closed trades, after fees and funding"
            action={
              performance.data?.stats.live_trades ? <Badge tone="warn">includes live</Badge> : <DemoBadge />
            }
          />
          <PanelBody>
            {performance.loading ? (
              <Skeleton className="h-44 w-full" />
            ) : cumulative.length > 1 ? (
              <>
                <AreaChart
                  values={cumulative}
                  tone={cumulative[cumulative.length - 1]! >= 0 ? "gold" : "loss"}
                  labels={curve.length ? [curve[0]!.date, curve[curve.length - 1]!.date] : undefined}
                  ariaLabel="Cumulative net profit and loss over closed trades"
                />
                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line-soft pt-4 sm:grid-cols-4">
                  {[
                    ["Trades", `${performance.data?.stats.trades ?? 0}`],
                    ["Win rate", percent(performance.data?.stats.win_rate_pct)],
                    ["Profit factor", performance.data?.stats.profit_factor ?? "—"],
                    ["Max drawdown", percent(performance.data?.stats.max_drawdown_pct)],
                  ].map(([label, value]) => (
                    <div key={String(label)}>
                      <p className="label">{label}</p>
                      <p className="num mt-1 text-sm text-paper">{value}</p>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState
                title="No closed trades yet"
                description="Paper trades appear here once a position is closed. Nothing is back-filled or estimated."
                action={
                  <Link href="/app/terminal">
                    <Button size="sm" variant="secondary">
                      Open the terminal
                    </Button>
                  </Link>
                }
              />
            )}
          </PanelBody>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHeader title="Live readiness" subtitle="Every gate is enforced server-side" />
            <PanelBody className="space-y-3">
              <ReadinessRow label="Plan permits live trading" ok={Boolean(entitlements?.features?.live_trading)} />
              <ReadinessRow label="Platform execution gate" ok={Boolean(platform?.live_trading_enabled)} />
              <ReadinessRow
                label="Your authorisation"
                ok={live?.status === "authorized"}
                detail={live?.status ? titleCase(live.status) : "Not started"}
              />
              <ReadinessRow label="Kill switch clear" ok={!killEngaged} />
              <p className="pt-1 text-2xs leading-relaxed text-paper-faint">
                Live orders need all four plus a passing risk evaluation per order.{" "}
                {platform?.live_trading_enabled ? "" : "The platform gate is closed, so no live order can execute."}
              </p>
              <Link href="/app/settings#live" className="inline-flex items-center gap-1 text-xs text-champagne-300">
                Review authorisation <ArrowRight className="h-3 w-3" />
              </Link>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader
              title="Plan"
              subtitle={subscription?.plan_code ? `${titleCase(subscription.plan_code)} tier` : "Free tier"}
            />
            <PanelBody className="space-y-3">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-paper-muted">Status</span>
                <StatusBadge status={subscription?.status ?? "active"} />
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-paper-muted">Renews</span>
                <span className="num text-xs text-paper">
                  {subscription?.plan_code === "free" ? "Not applicable" : dateTime(subscription?.current_period_end ?? null)}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-paper-muted">Connections</span>
                <span className="num text-xs text-paper">
                  {portfolio.data?.connections.length ?? 0} / {entitlements?.limits?.max_connections ?? "—"}
                </span>
              </div>
              <Link href="/app/billing">
                <Button variant="secondary" size="sm" fullWidth>
                  <CircleDollarSign className="h-3.5 w-3.5" />
                  Manage billing
                </Button>
              </Link>
            </PanelBody>
          </Panel>
        </div>
      </div>

      <Panel>
        <PanelHeader
          title="Open positions"
          subtitle="Marked at the latest available price"
          action={
            <Link href="/app/portfolio" className="text-xs text-paper-muted transition hover:text-paper">
              Portfolio
            </Link>
          }
        />
        {portfolio.loading ? (
          <div className="p-5">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : portfolio.data && portfolio.data.positions.length > 0 ? (
          <Table>
            <THead>
              <TR>
                <TH>Instrument</TH>
                <TH>Side</TH>
                <TH align="right">Quantity</TH>
                <TH align="right">Entry</TH>
                <TH align="right">Mark</TH>
                <TH align="right">Unrealised</TH>
                <TH>Mode</TH>
              </TR>
            </THead>
            <TBody>
              {portfolio.data.positions.map((position) => (
                <TR key={position.id}>
                  <TD mono>{position.symbol}</TD>
                  <TD>
                    <Badge tone={position.side === "long" ? "gain" : "loss"}>{position.side}</Badge>
                  </TD>
                  <TD align="right" mono>
                    {position.quantity}
                  </TD>
                  <TD align="right" mono>
                    {money(position.avg_entry_price)}
                  </TD>
                  <TD align="right" mono>
                    {position.mark_price ? money(position.mark_price) : "—"}
                  </TD>
                  <TD align="right" mono>
                    <span className={position.unrealized_pnl >= 0 ? "text-gain" : "text-loss"}>
                      {signedMoney(position.unrealized_pnl)}
                    </span>
                  </TD>
                  <TD>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={position.mode} />
                      {position.mode === "paper" ? <DemoBadge /> : null}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState
            title="No open positions"
            description="Positions you open in the terminal appear here with live marks."
            icon={<Gauge className="h-5 w-5" />}
          />
        )}
      </Panel>

      <Panel>
        <PanelHeader
          title="Recent closed trades"
          subtitle="Select a row for the full record: risk checks, costs, slippage, intervention"
          action={
            <Link href="/app/portfolio" className="text-xs text-paper-muted transition hover:text-paper">
              All trades
            </Link>
          }
        />
        {trades.loading ? (
          <div className="p-5">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : trades.data && trades.data.trades.length > 0 ? (
          <Table>
            <THead>
              <TR>
                <TH>Instrument</TH>
                <TH>Side</TH>
                <TH align="right">Net P&amp;L</TH>
                <TH align="right">Fees</TH>
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
                    <span className={trade.net_pnl >= 0 ? "text-gain" : "text-loss"}>
                      {signedMoney(trade.net_pnl)}
                    </span>
                  </TD>
                  <TD align="right" mono>
                    {money(trade.fees, "USD", 2)}
                  </TD>
                  <TD>{dateTime(trade.closed_at)}</TD>
                  <TD>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={trade.mode} />
                      {trade.is_demo ? <DemoBadge /> : null}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState
            title="No trades recorded"
            description="Trade records are immutable once written. Simulated trades are marked as such everywhere."
            icon={<ShieldCheck className="h-5 w-5" />}
          />
        )}
      </Panel>

      {!platform?.live_trading_enabled ? (
        <div className="flex items-start gap-3 rounded-xl border border-line-soft bg-ink-900/60 px-5 py-4">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
          <p className="text-xs leading-relaxed text-paper-faint">
            Live execution is disabled platform-wide. Every strategy runs in simulation until an operator verifies
            venue connectivity and opens the gate. No figure on this page is a forecast.
          </p>
        </div>
      ) : null}

      <TradeDetailDialog tradeId={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
}

function ReadinessRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-paper-muted">{label}</span>
      {ok ? <Badge tone="gain">ready</Badge> : <Badge tone="neutral">{detail ?? "pending"}</Badge>}
    </div>
  );
}
