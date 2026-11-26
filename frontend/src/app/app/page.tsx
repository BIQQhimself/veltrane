"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CircleDollarSign,
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
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { money, signedMoney } from "@/lib/format";
import { AreaChart } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
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
    paper_trades: number;
    live_trades: number;
  };
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
          tone === "gain" && "text-emerald-300",
          tone === "loss" && "text-loss",
          tone === "info" && "text-electric-300",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-3xs text-paper-faint">{hint}</p> : null}
    </div>
  );
}

function GaugeRow({ label, value, cap, hint }: { label: string; value: number; cap: number; hint?: string }) {
  const ratio = cap > 0 ? Math.min(1, value / cap) : 0;
  const danger = ratio > 0.8;
  return (
    <div>
      <div className="flex items-baseline justify-between text-2xs">
        <span className="text-paper-faint">{label}</span>
        <span className={cn("num", danger ? "text-loss" : "text-paper-muted")}>
          {value.toFixed(2)} / {cap.toFixed(2)}
        </span>
      </div>
      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-obsidian-750">
        <div
          className={cn("h-full rounded-full transition-all", danger ? "bg-loss" : "bg-gradient-to-r from-electric-500 to-emerald-400")}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
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

  const equity = portfolio.data?.equity;
  const stats = performance.data?.stats;
  const curve = (performance.data?.curve ?? []).map((point) => point.cumulative);
  const openContracts = (binary.data?.contracts ?? []).filter((c) => c.status === "open");
  const summary = binary.data?.summary;
  const killEngaged = Boolean((state.data?.kill_switches as Record<string, { engaged?: boolean }> | undefined)?.org?.engaged);
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
  const topAssets = (assets.data?.assets ?? []).slice(0, 6);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-2xs uppercase tracking-label text-paper-faint">
            {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </p>
          <h1 className="mt-1 font-display text-2xl font-semibold tracking-tight text-paper">
            Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"},{" "}
            {firstName}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Badge tone="info">{plan}</Badge>
            <Badge tone={killEngaged ? "loss" : "gain"}>
              {killEngaged ? "Trading halted" : "Trading armed"}
            </Badge>
            <Badge tone={platform?.live_trading_enabled ? "warn" : "neutral"}>
              {platform?.live_trading_enabled ? "Live gate open" : "Live disabled"}
            </Badge>
            <Badge tone="warn">Simulated</Badge>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/app/terminal"
            className="cta-gold inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-medium transition"
          >
            <Zap className="h-3.5 w-3.5" aria-hidden />
            Open terminal
          </Link>
          <Link
            href="/app/copilot"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3.5 py-2 text-xs text-paper transition hover:border-electric-600/60"
          >
            <Bot className="h-3.5 w-3.5 text-electric-300" aria-hidden />
            Ask the copilot
          </Link>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Simulated equity"
          value={equity ? money(equity.simulated_balance_usd) : "—"}
          hint={equity?.simulated_source === "paper_session" ? "Paper session equity" : "No paper session yet"}
          icon={CircleDollarSign}
        />
        <Metric
          label="Realised net P&L"
          value={equity ? signedMoney(equity.realized_pnl_net) : "—"}
          hint="After fees and funding, all modes"
          tone={(equity?.realized_pnl_net ?? 0) >= 0 ? "gain" : "loss"}
          icon={TrendingUp}
        />
        <Metric
          label="Open contracts"
          value={String(openContracts.length)}
          hint={summary ? `${money(summary.open_stake)} staked` : "Fixed-odds positions"}
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

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
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
            ) : curve.length > 1 ? (
              <AreaChart values={curve} height={190} tone={(curve.at(-1) ?? 0) >= 0 ? "gain" : "loss"} ariaLabel="Equity curve" />
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
                  <Link href="/app/terminal" className="text-2xs text-electric-300 hover:text-electric-200">
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
              ["Trades", stats ? `${stats.paper_trades} paper · ${stats.live_trades} live` : "—", null],
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
            <Badge tone={killEngaged ? "loss" : "gain"}>{killEngaged ? "Halted" : "Within limits"}</Badge>
          </div>
          <div className="flex-1 space-y-4 p-4">
            <GaugeRow
              label="Open stake vs equity"
              value={summary?.open_stake ?? 0}
              cap={Math.max(1, (equity?.simulated_balance_usd ?? 0) * 0.3)}
              hint="Account exposure cap is 30% of equity"
            />
            <GaugeRow
              label="Demo executions"
              value={demoUsed}
              cap={demoLimit}
              hint="Shared by spot and fixed-odds contracts"
            />
            <GaugeRow
              label="Daily loss limit"
              value={Math.max(0, -(stats?.net_pnl ?? 0))}
              cap={Math.max(1, (equity?.simulated_balance_usd ?? 0) * 0.03)}
              hint="Breaching 3% halts new risk until the next session"
            />
            <div className="rounded-lg border border-line-soft bg-obsidian-900/50 p-3">
              <p className="flex items-center gap-1.5 text-2xs text-paper-muted">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" aria-hidden />
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
              <Link href="/app/settings" className="mt-2 inline-flex items-center gap-1 text-3xs text-electric-300 hover:text-electric-200">
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
            <Link href="/app/markets" className="text-3xs text-electric-300 hover:text-electric-200">
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
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-obsidian-800 font-mono text-3xs text-paper-muted">
                        {asset.base.slice(0, 3)}
                      </span>
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
                        href="/app/terminal"
                        className="flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-3xs text-emerald-300 transition hover:bg-emerald-500/20"
                      >
                        <ArrowUpRight className="h-3 w-3" aria-hidden />
                        Call
                      </Link>
                      <Link
                        href="/app/terminal"
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
                <Bot className="h-3.5 w-3.5 text-electric-300" aria-hidden />
                Copilot briefing
              </h2>
              <p className="mt-0.5 text-3xs text-paper-faint">Deterministic technical reads · not advice</p>
            </div>
            <Link href="/app/copilot" className="text-3xs text-electric-300 hover:text-electric-200">
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
                        ? "bg-emerald-500/10 text-emerald-300"
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
            <Link href="/app/terminal" className="text-3xs text-electric-300 hover:text-electric-200">
              Manage →
            </Link>
          </div>
          <ul className="divide-y divide-line-soft">
            {openContracts.map((contract) => (
              <li key={contract.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                <span className="flex items-center gap-2">
                  <span className={contract.direction === "call" ? "text-emerald-300" : "text-loss"}>
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
            <p className="mt-0.5 text-3xs text-paper-faint">Every trade opens into its full risk and cost record</p>
          </div>
          <Link href="/app/portfolio" className="text-3xs text-electric-300 hover:text-electric-200">
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
                      {trade.entry_price} → {trade.exit_price}
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
