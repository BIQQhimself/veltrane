"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Clock,
  Gauge,
  Layers,
  ShieldCheck,
  Target,
  Timer,
  TrendingUp,
  Zap,
} from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { byAssetClass } from "@/lib/assets";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { money, price, signedMoney } from "@/lib/format";
import { AreaChart } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { RiskBudgetRows } from "@/components/app/risk-budget";
import { AccountHero } from "@/components/app/account-hero";
import { AutomationStrip } from "@/components/app/automation-strip";
import { TierBadge } from "@/components/app/tier-badge";
import { PageHeader } from "@/components/ui/panel";
import { contractReturn, contractStake } from "@/lib/contracts";
import { budgetLabel, budgetTone, type RiskBudget } from "@/lib/risk-budget";
import { TradeDetailDialog } from "@/components/app/trade-detail";
import { cn } from "@/lib/cn";
import type { BinaryAsset, BinaryContract, BinarySummary, PortfolioOverview, Trade, TradingState } from "@/lib/types";

type Performance = {
  curve: Array<{ date: string; pnl: number; cumulative: number }>;
  stats: {
    trades: number;
    win_rate_pct: number;
    profit_factor: number | null;
    net_pnl: number;
    max_drawdown_pct: number;
  };
  trade_counts: { paper: number; demo: number; live: number };
};

type Briefing = { rows: Array<{ symbol: string; asset_class: string; price: number; bias: string; confidence: number; is_demo: boolean }> };

function Metric({
  label,
  value,
  hint,
  tone = "default",
  icon: Icon,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "gain" | "loss" | "info";
  icon?: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
}) {
  return (
    <div className="panel relative overflow-hidden p-4">
      <div className="flex items-start justify-between">
        <p className="label">{label}</p>
        {Icon ? <Icon className="h-3.5 w-3.5 text-paper-faint" aria-hidden /> : null}
      </div>
      <p
        className={cn(
          "stat-value mt-2",
          tone === "gain" && "text-gain",
          tone === "loss" && "text-loss",
          tone === "info" && "text-champagne-300",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-3xs text-paper-faint">{hint}</p> : null}
    </div>
  );
}

export default function OverviewPage() {
  const { user, entitlements, usage, live, platform } = useAuth();
  const [selectedTrade, setSelectedTrade] = React.useState<string | null>(null);
  const [provisioning, setProvisioning] = React.useState(false);
  const toast = useToast();

  const portfolio = useApi<PortfolioOverview>((signal) => api("/portfolio/overview", { signal }));
  const performance = useApi<Performance>((signal) => api("/portfolio/performance", { signal }));
  const state = useApi<TradingState>((signal) => api("/trading/state", { signal }));
  const trades = useApi<{ trades: Trade[] }>((signal) => api("/trades", { signal, query: { limit: 8 } }));
  const binary = useApi<{ contracts: BinaryContract[]; summary: BinarySummary }>((signal) =>
    api("/binary/contracts", { signal, query: { limit: 40 } }),
  );
  const assets = useApi<{ assets: BinaryAsset[] }>((signal) => api("/binary/assets", { signal }));
  const briefing = useApi<Briefing>((signal) => api("/copilot/briefing", { signal }));
  const riskBudget = useApi<RiskBudget>((signal) => api("/trading/risk-budget", { signal }));

  const equity = portfolio.data?.equity;
  const stats = performance.data?.stats;
  const counts = performance.data?.trade_counts ?? { paper: 0, demo: 0, live: 0 };
  const dailyCurve = (performance.data?.curve ?? []).map((point) => point.cumulative);
  const curve = dailyCurve;
  const openContracts = (binary.data?.contracts ?? []).filter((c) => c.status === "open");
  const killEngaged = Boolean((state.data?.kill_switches as Record<string, { engaged?: boolean }> | undefined)?.org?.engaged);
  const riskLabel = budgetLabel(riskBudget.data, killEngaged);
  const riskTone = budgetTone(riskBudget.data, killEngaged);
  const demoLimit = Number(entitlements?.limits?.max_daily_demo_executions ?? 5);
  const demoUsed = usage?.demo_executions_today ?? 0;
  const plan = entitlements?.plan_code ?? "free";

  const startPaperSession = async () => {
    setProvisioning(true);
    try {
      await api("/trading/paper-session", { method: "POST" });
      toast.success("Paper account ready", "25,000.00 of simulated capital is now available.");
      portfolio.refetch();
      state.refetch();
    } catch (error) {
      toast.error("Could not start the paper session", errorMessage(error));
    } finally {
      setProvisioning(false);
    }
  };

  const firstName = (user?.full_name ?? "Trader").split(" ")[0];
  const now = new Date();
  const greeting = {
    day: now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }),
    title: `Good ${now.getHours() < 12 ? "morning" : now.getHours() < 18 ? "afternoon" : "evening"}, ${firstName}`,
  };
  const topAssets = [...(assets.data?.assets ?? [])].sort(byAssetClass).slice(0, 6);
  // The risk engine charges spot/CFD notional against the same 30% cap, so the
  // posture panel must count it or it reads as zero exposure while a trade is open.
  return (
    <div className="space-y-4">
      {/* Header */}
      <PageHeader
        eyebrow={greeting.day}
        title={greeting.title}
        badge={
          <>
            <TierBadge planCode={plan} size="xs" />
            <Badge tone={killEngaged ? "loss" : "neutral"}>
              {killEngaged ? "Kill switch engaged" : "Kill switch released"}
            </Badge>
            <Badge tone={platform?.live_trading_enabled ? "warn" : "neutral"}>
              {platform?.live_trading_enabled ? "Live gate open" : "Live disabled"}
            </Badge>
            <Badge tone="warn">Simulated</Badge>
          </>
        }
        action={
          <>
            <Link
              href="/app/terminal"
              className="cta-gold inline-flex items-center gap-1.5 rounded-full px-4 py-2.5 text-xs font-semibold transition"
            >
              <Zap className="h-3.5 w-3.5" aria-hidden />
              Open terminal
            </Link>
            <Link
              href="/app/copilot"
              className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-4 py-2.5 text-xs text-paper transition hover:bg-white/[0.04]"
            >
              <Bot className="h-3.5 w-3.5 text-paper-muted" aria-hidden />
              Ask the copilot
            </Link>
          </>
        }
      />

      <AutomationStrip />

      <AccountHero
        planCode={plan}
        equityLabel={equity?.simulated_source === "paper_session" ? "Paper session equity" : "Account value"}
        equity={equity ? equity.simulated_balance_usd : null}
        netPnl={equity ? equity.realized_pnl_net : null}
        curve={curve}
        openTrades={openContracts.length + (portfolio.data?.positions.length ?? 0)}
        demoUsed={demoUsed}
        demoLimit={demoLimit}
        riskLabel={riskLabel}
        riskTone={riskTone}
        simulated
        paperReady={Boolean(portfolio.data?.paper_session)}
        onStartPaper={startPaperSession}
      />

      {/* Metrics */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric
          label="Realised net P&L"
          value={equity ? signedMoney(equity.realized_pnl_net) : "—"}
          hint="After fees and funding, all modes"
          tone={(equity?.realized_pnl_net ?? 0) >= 0 ? "gain" : "loss"}
          icon={TrendingUp}
        />
        <Metric
          label="Open trades"
          value={String(openContracts.length + (portfolio.data?.positions.length ?? 0))}
          hint={`${openContracts.length} contract${openContracts.length === 1 ? "" : "s"} · ${
            portfolio.data?.positions.length ?? 0
          } CFD/spot`}
          icon={Timer}
        />
        <Metric
          label="Demo executions"
          value={`${demoUsed} / ${demoLimit}`}
          hint={demoUsed >= demoLimit ? "Daily cap reached — upgrade for more" : "Resets at 00:00 UTC"}
          tone={demoUsed >= demoLimit ? "loss" : "info"}
          icon={Target}
        />
      </div>

      <div className="grid items-start gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        {/* Equity curve */}
        <section className="panel">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft px-4 py-3">
            <div>
              <h2 className="text-sm font-medium text-paper">Equity curve</h2>
              <p className="mt-0.5 text-3xs text-paper-faint">
                Cumulative realised P&L, net of costs · {stats?.trades ?? 0} closed trades
              </p>
            </div>
            <div className="flex items-center gap-3 text-2xs">
              <span className="text-paper-faint">
                Win rate <span className="num text-paper">{stats ? `${stats.win_rate_pct.toFixed(1)}%` : "—"}</span>
              </span>
              <span className="text-paper-faint">
                Profit factor <span className="num text-paper">{stats?.profit_factor ?? "—"}</span>
              </span>
            </div>
          </div>
          <div className="px-3 pb-2 pt-4">
            {performance.loading && !performance.data ? (
              <div className="shimmer h-[190px] rounded-lg" />
            ) : curve.length >= 3 ? (
              <AreaChart
                values={curve}
                height={230}
                tone={(curve.at(-1) ?? 0) >= 0 ? "gain" : "loss"}
                ariaLabel="Cumulative realised P&L by day"
                formatValue={signedMoney}
              />
            ) : curve.length > 0 ? (
              // One or two days cannot show a trend; a line across them reads as a collapse.
              <div className="flex h-[190px] flex-col items-center justify-center text-center">
                <p className="text-xs text-paper-muted">
                  {curve.length === 1 ? "One trading day so far" : "Two trading days so far"}
                </p>
                <p className={`num mt-2 text-2xl ${(curve.at(-1) ?? 0) >= 0 ? "text-gain" : "text-loss"}`}>
                  {signedMoney(curve.at(-1) ?? 0)}
                </p>
                <p className="mt-1 max-w-xs text-3xs text-paper-faint">
                  Cumulative realised P&amp;L after costs. The curve is drawn once there are three trading days.
                </p>
              </div>
            ) : (
              <div className="flex h-[190px] flex-col items-center justify-center text-center">
                <TrendingUp className="h-5 w-5 text-paper-faint" aria-hidden />
                <p className="mt-2 text-xs text-paper-muted">No closed trades yet</p>
                <p className="mt-1 max-w-xs text-3xs text-paper-faint">
                  Open a contract in the terminal and let it settle, or run a strategy in paper mode.
                </p>
                <div className="mt-3 flex items-center gap-3">
                  {portfolio.data?.paper_session ? null : (
                    <Button size="sm" variant="secondary" loading={provisioning} onClick={startPaperSession}>
                      Start paper account
                    </Button>
                  )}
                  <Link href="/app/terminal" className="text-2xs text-champagne-300 hover:text-champagne-200">
                    Go to the terminal →
                  </Link>
                </div>
              </div>
            )}
          </div>
          <div className="grid grid-cols-3 divide-x divide-line-soft border-t border-line-soft">
            {[
              ["Net P&L", stats ? signedMoney(stats.net_pnl) : "—", (stats?.net_pnl ?? 0) >= 0],
              ["Max drawdown", stats ? `${stats.max_drawdown_pct.toFixed(2)}%` : "—", null],
              [
                "Trades",
                stats
                  ? `${counts.paper} paper · ${counts.demo} demo · ${counts.live} live`
                  : "—",
                null,
              ],
            ].map(([label, value, positive]) => (
              <div key={label as string} className="px-4 py-2.5">
                <p className="text-3xs uppercase tracking-label text-paper-faint">{label}</p>
                <p
                  className={cn(
                    "num mt-0.5 text-xs",
                    positive === true ? "text-gain" : positive === false ? "text-loss" : "text-paper",
                  )}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Risk + mode */}
        <section className="panel flex flex-col">
          <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
            <h2 className="text-sm font-medium text-paper">Risk posture</h2>
            <Badge tone={riskTone}>{riskLabel}</Badge>
          </div>
          <div className="flex-1 space-y-4 p-4">
            <RiskBudgetRows budget={riskBudget.data} />
            <p className="text-3xs text-paper-faint">
              Read from the same rules the risk engine applies to the next order. Headroom is paper-only.
            </p>
            <div className="rounded-lg border border-line-soft bg-obsidian-900/50 p-3">
              <p className="flex items-center gap-1.5 text-2xs text-paper-muted">
                <ShieldCheck className="h-3.5 w-3.5 text-gain" aria-hidden />
                Independent risk engine
              </p>
              <p className="mt-1 text-3xs leading-relaxed text-paper-faint">
                Every order and contract is evaluated by the deterministic engine before execution.
                Strategies cannot bypass it, and the kill switch works without this app open.
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {["size", "exposure", "leverage", "daily loss", "drawdown", "stale data", "duplicates"].map((rule) => (
                  <span key={rule} className="rounded border border-line px-1.5 py-0.5 text-3xs text-paper-faint">
                    {rule}
                  </span>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-line-soft bg-obsidian-900/50 p-3">
              <p className="text-2xs text-paper-muted">Live trading</p>
              <p className="mt-1 text-3xs leading-relaxed text-paper-faint">
                {live?.status === "authorized"
                  ? "Authorised for this organisation. The platform gate still governs routing."
                  : "Not authorised. Paper execution only until the safety checklist is completed."}
              </p>
              <Link href="/app/settings" className="mt-2 inline-flex items-center gap-1 text-3xs text-champagne-300 hover:text-champagne-200">
                Review authorisation <ArrowRight className="h-3 w-3" aria-hidden />
              </Link>
            </div>
          </div>
        </section>
      </div>

      {/* Quick trade + briefing */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <section className="panel">
          <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
            <div>
              <h2 className="text-sm font-medium text-paper">Quick trade</h2>
              <p className="mt-0.5 text-3xs text-paper-faint">5-minute payout per asset · simulated book</p>
            </div>
            <Link href="/app/markets" className="text-3xs text-champagne-300 hover:text-champagne-200">
              All markets →
            </Link>
          </div>
          <ul className="divide-y divide-line-soft">
            {assets.loading
              ? Array.from({ length: 4 }).map((_, index) => (
                  <li key={index} className="px-4 py-3">
                    <div className="shimmer h-8 rounded" />
                  </li>
                ))
              : topAssets.map((asset) => (
                  <li key={asset.symbol} className="flex items-center justify-between gap-3 px-4 py-2.5">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <span
                        aria-hidden
                        className={cn(
                          "h-8 w-1 rounded-full",
                          asset.asset_class === "crypto"
                            ? "bg-gold-400/70"
                            : asset.asset_class === "forex"
                              ? "bg-champagne-500"
                              : "bg-paper-faint/40",
                        )}
                      />
                      <div className="min-w-0">
                        <p className="truncate font-mono text-xs text-paper">{asset.symbol}</p>
                        <p className="truncate text-3xs text-paper-faint">
                          {asset.name} · {asset.asset_class}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="num hidden text-3xs text-paper-faint sm:block">
                        {asset.payouts?.["300"] ?? "—"}% payout
                      </span>
                      <Link
                        href={`/app/terminal?symbol=${encodeURIComponent(asset.symbol)}`}
                        className="flex items-center gap-1 rounded-md border border-gain/30 bg-gain/10 px-2 py-1 text-3xs text-gain transition hover:bg-gain/20"
                      >
                        <ArrowUpRight className="h-3 w-3" aria-hidden />
                        Call
                      </Link>
                      <Link
                        href={`/app/terminal?symbol=${encodeURIComponent(asset.symbol)}`}
                        className="flex items-center gap-1 rounded-md border border-loss/30 bg-loss/10 px-2 py-1 text-3xs text-loss transition hover:bg-loss/20"
                      >
                        <ArrowDownRight className="h-3 w-3" aria-hidden />
                        Put
                      </Link>
                    </div>
                  </li>
                ))}
          </ul>
        </section>

        <section className="panel">
          <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
            <div>
              <h2 className="flex items-center gap-1.5 text-sm font-medium text-paper">
                <Bot className="h-3.5 w-3.5 text-champagne-300" aria-hidden />
                Copilot briefing
              </h2>
              <p className="mt-0.5 text-3xs text-paper-faint">Deterministic technical reads · not advice</p>
            </div>
            <Link href="/app/copilot" className="text-3xs text-champagne-300 hover:text-champagne-200">
              Open →
            </Link>
          </div>
          <ul className="divide-y divide-line-soft">
            {briefing.loading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <li key={index} className="px-4 py-3">
                  <div className="shimmer h-6 rounded" />
                </li>
              ))
            ) : (briefing.data?.rows ?? []).slice(0, 5).map((row) => (
              <li key={row.symbol} className="flex items-center justify-between gap-2 px-4 py-2.5">
                <span className="font-mono text-xs text-paper">{row.symbol}</span>
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-3xs uppercase tracking-label",
                      row.bias === "call"
                        ? "bg-gain/10 text-gain"
                        : row.bias === "put"
                          ? "bg-loss/10 text-loss"
                          : "bg-obsidian-750 text-paper-faint",
                    )}
                  >
                    {row.bias}
                  </span>
                  <span className="num text-3xs text-paper-faint">{row.confidence}%</span>
                </div>
              </li>
            ))}
          </ul>
          <p className="border-t border-line-soft px-4 py-2 text-3xs text-paper-faint">
            Reads are computed from the candles shown in the terminal. They can be wrong and are never
            a guarantee.
          </p>
        </section>
      </div>

      {/* Open contracts */}
      {openContracts.length ? (
        <section className="panel">
          <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
            <h2 className="flex items-center gap-1.5 text-sm font-medium text-paper">
              <Clock className="h-3.5 w-3.5 text-warn" aria-hidden />
              Open contracts
            </h2>
            <Link href="/app/terminal" className="text-3xs text-champagne-300 hover:text-champagne-200">
              Manage →
            </Link>
          </div>
          <ul className="divide-y divide-line-soft">
            {openContracts.map((contract) => (
              <li key={contract.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                <span className="flex items-center gap-2">
                  <span className={contract.direction === "call" ? "text-gain" : "text-loss"}>
                    {contract.direction === "call" ? (
                      <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
                    ) : (
                      <ArrowDownRight className="h-3.5 w-3.5" aria-hidden />
                    )}
                  </span>
                  <span className="font-mono text-xs text-paper">{contract.symbol}</span>
                  <span className="text-3xs text-paper-faint">
                    {money(contract.stake)} · {contract.payout_pct}%
                  </span>
                </span>
                <span className="num text-3xs text-paper-muted">
                  expires {new Date(contract.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Recent trades */}
      <section className="panel">
        <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
          <div>
            <h2 className="text-sm font-medium text-paper">Recent trades</h2>
            <p className="mt-0.5 text-3xs text-paper-faint">
              Every trade opens into its full risk and cost record. Fixed-odds contracts show stake → return.
            </p>
          </div>
          <Link href="/app/portfolio" className="text-3xs text-champagne-300 hover:text-champagne-200">
            Full history →
          </Link>
        </div>
        {(trades.data?.trades ?? []).length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
            <Layers className="h-5 w-5 text-paper-faint" aria-hidden />
            <p className="mt-2 text-xs text-paper-muted">No trades yet</p>
            <p className="mt-1 max-w-sm text-3xs text-paper-faint">
              Paper trades and settled contracts appear here with their entry reason, risk checks and
              after-cost P&L.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead>
                <tr className="border-b border-line-soft text-3xs uppercase tracking-label text-paper-faint">
                  <th className="px-4 py-2 font-normal">Symbol</th>
                  <th className="px-4 py-2 font-normal">Side</th>
                  <th className="px-4 py-2 text-right font-normal">Entry → exit</th>
                  <th className="px-4 py-2 text-right font-normal">Net</th>
                  <th className="px-4 py-2 text-right font-normal">Closed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {(trades.data?.trades ?? []).map((trade) => (
                  <tr
                    key={trade.id}
                    onClick={() => setSelectedTrade(trade.id)}
                    className="cursor-pointer hover:bg-obsidian-800/40"
                  >
                    <td className="px-4 py-2.5">
                      <span className="font-mono text-paper">{trade.symbol}</span>
                      {trade.is_demo ? <span className="ml-2 text-3xs text-warn/70">sim</span> : null}
                    </td>
                    <td className="px-4 py-2.5 text-paper-muted">{trade.side}</td>
                    <td className="num px-4 py-2.5 text-right text-paper-muted">
                      {contractStake(trade) !== null ? (
                        <>
                          {money(contractStake(trade))} stake → {money(contractReturn(trade)?.value ?? trade.exit_price)}
                        </>
                      ) : (
                        <>
                          {price(trade.entry_price)} → {price(trade.exit_price)}
                        </>
                      )}
                    </td>
                    <td className={cn("num px-4 py-2.5 text-right", trade.net_pnl >= 0 ? "text-gain" : "text-loss")}>
                      {signedMoney(trade.net_pnl)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-3xs text-paper-faint">
                      {new Date(trade.closed_at ?? 0).toLocaleString([], {
                        month: "short",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line-soft bg-obsidian-900/40 px-4 py-3">
        <p className="flex items-center gap-1.5 text-3xs text-paper-faint">
          <Gauge className="h-3 w-3" aria-hidden />
          Data source: {state.data?.data_source_mode ?? "—"} · {state.data?.demo_executions_today ?? 0} demo
          executions today
        </p>
        <p className="text-3xs text-paper-faint">
          Simulated results are not predictions. VELTRANE never holds your funds.
        </p>
      </div>

      <TradeDetailDialog tradeId={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
}
