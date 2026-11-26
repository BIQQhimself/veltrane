"use client";

import * as React from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  Clock,
  Info,
  Minus,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Timer,
} from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { CandleChart, type Candle } from "@/components/charts/candles";
import type {
  BinaryAsset,
  BinaryContract,
  BinaryQuote,
  BinarySummary,
  CopilotRead,
} from "@/lib/types";

const DURATIONS = [
  { seconds: 60, label: "1m" },
  { seconds: 300, label: "5m" },
  { seconds: 900, label: "15m" },
  { seconds: 1800, label: "30m" },
  { seconds: 3600, label: "1h" },
];

const TIMEFRAMES = ["1m", "5m", "15m", "1h"] as const;

const CLASS_LABEL: Record<string, string> = {
  crypto: "Crypto",
  forex: "Forex",
  stock: "Equities",
  commodity: "Metals",
};

function fmtPrice(value: number) {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Math.abs(value) >= 10) return value.toFixed(3);
  if (Math.abs(value) >= 1) return value.toFixed(4);
  return value.toFixed(5);
}

function money(value: number) {
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

function useCountdown(target: string | null) {
  const [remaining, setRemaining] = React.useState(0);
  React.useEffect(() => {
    if (!target) return;
    const tick = () => setRemaining(Math.max(0, Math.round((new Date(target).getTime() - Date.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [target]);
  return remaining;
}

function ContractCountdown({ expiresAt }: { expiresAt: string }) {
  const remaining = useCountdown(expiresAt);
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return (
    <span className={cn("num text-xs", remaining <= 10 ? "text-warn" : "text-paper")}>
      {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, { tone: "gain" | "loss" | "neutral" | "warn"; label: string }> = {
    open: { tone: "warn", label: "Open" },
    won: { tone: "gain", label: "Won" },
    lost: { tone: "loss", label: "Lost" },
    void: { tone: "neutral", label: "Void" },
    rejected: { tone: "loss", label: "Rejected" },
  };
  const entry = map[status] ?? { tone: "neutral" as const, label: status };
  return <Badge tone={entry.tone}>{entry.label}</Badge>;
}

export default function TerminalPage() {
  const toast = useToast();
  const [assetClass, setAssetClass] = React.useState<string>("all");
  const [query, setQuery] = React.useState("");
  const [symbol, setSymbol] = React.useState("BTC/USDT");
  const [deepLinkHandled, setDeepLinkHandled] = React.useState(false);
  const [timeframe, setTimeframe] = React.useState<(typeof TIMEFRAMES)[number]>("15m");
  const [duration, setDuration] = React.useState(300);
  const [direction, setDirection] = React.useState<"call" | "put">("call");
  const [stake, setStake] = React.useState(100);
  const [busy, setBusy] = React.useState(false);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [detailContract, setDetailContract] = React.useState<BinaryContract | null>(null);
  const [sheetTab, setSheetTab] = React.useState<"open" | "history">("open");
  const [lastRejection, setLastRejection] = React.useState<{ reason: string; rules: string[] } | null>(null);

  const assets = useApi<{ assets: BinaryAsset[] }>((signal) => api("/binary/assets", { signal }));
  const contracts = useApi<{ contracts: BinaryContract[]; summary: BinarySummary }>((signal) =>
    api("/binary/contracts", { signal, query: { limit: 60 } }),
  );
  const candles = useApi<{ candles: Candle[]; meta: { source: string; is_demo: boolean } }>((signal) =>
    api(`/markets/candles/${encodeURIComponent(symbol)}`, { signal, query: { timeframe, limit: 160 } }),
    [symbol, timeframe],
  );
  const quote = useApi<BinaryQuote>(
    (signal) => api("/binary/quote", { method: "POST", body: { symbol, duration_seconds: duration }, signal }),
    [symbol, duration],
  );
  const copilot = useApi<CopilotRead>(
    (signal) =>
      api("/copilot/analyse", {
        method: "POST",
        body: { symbol, timeframe: "15m", duration_seconds: duration },
        signal,
      }),
    [symbol, duration],
  );

  const assetList = React.useMemo(() => assets.data?.assets ?? [], [assets.data]);
  const filtered = React.useMemo(() => {
    return assetList.filter((asset) => {
      const classOk = assetClass === "all" || asset.asset_class === assetClass;
      const queryOk =
        !query ||
        asset.symbol.toLowerCase().includes(query.toLowerCase()) ||
        asset.name.toLowerCase().includes(query.toLowerCase());
      return classOk && queryOk;
    });
  }, [assetList, assetClass, query]);

  const activeAsset = assetList.find((asset) => asset.symbol === symbol);
  const openContracts = (contracts.data?.contracts ?? []).filter((c) => c.status === "open");
  const settledContracts = (contracts.data?.contracts ?? []).filter((c) => c.status !== "open");
  const summary = contracts.data?.summary;
  const payout = quote.data?.payout_pct ?? Number(activeAsset?.payouts?.[String(duration)] ?? 0);
  const potentialReturn = (stake * payout) / 100;
  const quoteMatchesSymbol = quote.data?.symbol === symbol;
  const livePrice = (quoteMatchesSymbol ? quote.data?.price : undefined) ?? candles.data?.candles.at(-1)?.close ?? 0;
  const isDemoFeed = candles.data?.meta?.is_demo ?? true;

  // Deep link from Markets: /app/terminal?symbol=ETH%2FUSDT
  React.useEffect(() => {
    if (deepLinkHandled || !assetList.length) return;
    const requested = new URLSearchParams(window.location.search).get("symbol");
    setDeepLinkHandled(true);
    if (!requested) return;
    setSymbol((current) => {
      const match = assetList.find((asset) => asset.symbol.toLowerCase() === requested.toLowerCase());
      return match?.symbol ?? current;
    });
  }, [assetList, deepLinkHandled]);

  // Settlement is lazy server-side; poll while contracts are live so the UI converges.
  React.useEffect(() => {
    if (!openContracts.length) return;
    const timer = setInterval(() => contracts.refetch(), 5000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openContracts.length]);

  const submit = async () => {
    setBusy(true);
    setLastRejection(null);
    try {
      const result = await api<{
        approved: boolean;
        contract: BinaryContract;
        risk_decision: { failed_rules: Array<{ code: string; message: string }> } | null;
      }>("/binary/contracts", {
        method: "POST",
        body: { symbol, direction, stake, duration_seconds: duration, reason: `${direction.toUpperCase()} from terminal` },
      });
      if (result.approved) {
        toast.success(
          "Contract opened",
          `${direction.toUpperCase()} ${symbol} · ${money(stake)} at ${payout}% payout · simulated.`,
        );
        setSheetTab("open");
      } else {
        const rules = result.risk_decision?.failed_rules ?? [];
        setLastRejection({
          reason: result.contract.rejection_reason ?? "The risk engine rejected this contract.",
          rules: rules.map((rule) => rule.message),
        });
        toast.error("Contract rejected", result.contract.rejection_reason ?? "Risk engine refused the contract.");
      }
      contracts.refetch();
      setConfirmOpen(false);
    } catch (error) {
      toast.error("Could not open contract", errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const adjustStake = (delta: number) => {
    const min = quote.data?.min_stake ?? 10;
    const max = quote.data?.max_stake ?? 2000;
    setStake((value) => Math.min(max, Math.max(min, Math.round((value + delta) * 100) / 100)));
  };

  const bias = copilot.data?.bias ?? "neutral";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-xl font-semibold tracking-tight text-paper sm:text-2xl">
              Trading terminal
            </h1>
            <Badge tone="info">Fixed-odds</Badge>
            <Badge tone="warn">Simulated</Badge>
          </div>
          <p className="mt-1 text-xs text-paper-faint">
            Call or put, choose a duration, see the payout before you commit. Every contract passes the
            independent risk engine.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              contracts.refetch();
              quote.refetch();
              candles.refetch();
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-2.5 py-1.5 text-2xs text-paper-muted transition hover:text-paper"
          >
            <RefreshCw className="h-3 w-3" aria-hidden /> Refresh
          </button>
          <span className="chip">
            <Clock className="h-3 w-3" aria-hidden />
            {openContracts.length} open · {summary?.open_stake ? money(summary.open_stake) : money(0)} staked
          </span>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[236px_minmax(0,1fr)_320px]">
        {/* Asset rail */}
        <section className="panel order-3 flex flex-col xl:sticky xl:top-20 xl:order-1 xl:col-start-1 xl:row-start-1 xl:row-span-2 xl:max-h-[calc(100vh-6rem)] xl:self-start xl:overflow-hidden">
          <div className="shrink-0 border-b border-line-soft p-3">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-paper-faint" aria-hidden />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search assets"
                aria-label="Search assets"
                className="w-full rounded-lg border border-line bg-obsidian-900 py-2 pl-8 pr-2 text-xs text-paper outline-none transition focus:border-electric-500/60"
              />
            </label>
            <div className="mt-2 flex flex-wrap gap-1">
              {["all", "crypto", "forex", "stock", "commodity"].map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setAssetClass(key)}
                  className={cn(
                    "rounded px-1.5 py-1 text-3xs uppercase tracking-label transition",
                    assetClass === key ? "bg-electric-500/15 text-electric-200" : "text-paper-faint hover:text-paper-muted",
                  )}
                >
                  {key === "all" ? "All" : CLASS_LABEL[key]}
                </button>
              ))}
            </div>
          </div>
          <div className="max-h-[420px] min-h-0 flex-1 overflow-y-auto xl:max-h-none">
            {assets.loading ? (
              <div className="space-y-2 p-3">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div key={index} className="shimmer h-10 rounded-lg" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <p className="p-4 text-xs text-paper-faint">No assets match that search.</p>
            ) : (
              <ul className="divide-y divide-line-soft">
                {filtered.map((asset) => {
                  const active = asset.symbol === symbol;
                  const assetPayout = Number(asset.payouts?.[String(duration)] ?? 0);
                  return (
                    <li key={asset.symbol}>
                      <button
                        type="button"
                        onClick={() => setSymbol(asset.symbol)}
                        aria-current={active ? "true" : undefined}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left transition",
                          active ? "bg-electric-500/10" : "hover:bg-obsidian-800",
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-mono text-xs text-paper">{asset.symbol}</span>
                          <span className="block truncate text-3xs text-paper-faint">
                            {asset.name} · {CLASS_LABEL[asset.asset_class] ?? asset.asset_class}
                          </span>
                        </span>
                        <span className="shrink-0 text-right">
                          <span className="num block text-xs text-emerald-300">{assetPayout}%</span>
                          <span className="block text-3xs text-paper-faint">{DURATIONS.find((d) => d.seconds === duration)?.label}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <p className="shrink-0 border-t border-line-soft px-3 py-2 text-3xs leading-relaxed text-paper-faint">
            Indices are not offered. Payouts are platform modelling parameters for the simulated book.
          </p>
        </section>

        {/* Chart */}
        <section className="panel order-1 min-w-0 xl:col-start-2 xl:row-start-1 xl:self-start">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft px-4 py-3">
            <div className="flex items-center gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-mono text-sm text-paper">{symbol}</h2>
                  {isDemoFeed ? <Badge tone="warn">Simulated feed</Badge> : <Badge tone="gain">Live feed</Badge>}
                </div>
                <p className="mt-0.5 text-3xs text-paper-faint">
                  {activeAsset?.name ?? "—"} · {CLASS_LABEL[activeAsset?.asset_class ?? ""] ?? "—"}
                </p>
              </div>
              <div className="hidden items-baseline gap-2 sm:flex">
                <span className="num text-lg text-paper">{fmtPrice(livePrice)}</span>
                <span className="text-3xs text-paper-faint">
                  {quote.data?.price_source ? `source: ${quote.data.price_source}` : ""}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-1 rounded-lg border border-line-soft bg-obsidian-900/60 p-0.5">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  className={cn(
                    "rounded px-2 py-1 text-3xs transition",
                    timeframe === tf ? "bg-electric-500/20 text-electric-200" : "text-paper-faint hover:text-paper-muted",
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>

          <div className="relative">
            {candles.loading && !candles.data ? (
              <div className="shimmer m-4 h-[300px] rounded-lg" />
            ) : (
              <CandleChart
                candles={candles.data?.candles ?? []}
                height={330}
                livePrice={livePrice}
                entryPrice={openContracts.find((c) => c.symbol === symbol)?.entry_price ?? null}
                entryDirection={openContracts.find((c) => c.symbol === symbol)?.direction ?? null}
                ariaLabel={`${symbol} candlestick chart`}
              />
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 border-t border-line-soft p-3 sm:grid-cols-4">
            {[
              ["Bias", bias === "neutral" ? "Neutral" : bias === "call" ? "Call" : "Put", copilot.data ? `${copilot.data.confidence}% conf.` : "—"],
              ["RSI (15m)", copilot.data?.rsi != null ? copilot.data.rsi.toFixed(1) : "—", copilot.data?.momentum ?? "—"],
              ["ATR", copilot.data ? `${copilot.data.atr_pct.toFixed(2)}%` : "—", "14-bar volatility"],
              ["Open stake", summary ? money(summary.open_stake) : "—", `${openContracts.length} contracts`],
            ].map(([label, value, hint]) => (
              <div key={label} className="rounded-lg border border-line-soft bg-obsidian-900/50 px-2.5 py-2">
                <p className="text-3xs uppercase tracking-label text-paper-faint">{label}</p>
                <p className="num mt-0.5 text-sm text-paper">{value}</p>
                <p className="truncate text-3xs text-paper-faint">{hint}</p>
              </div>
            ))}
          </div>

          {copilot.data ? (
            <div className="border-t border-line-soft px-4 py-3">
              <div className="flex items-start gap-2">
                <Bot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-electric-300" aria-hidden />
                <div className="min-w-0">
                  <p className="text-2xs text-paper-muted">
                    <span className="text-paper">Copilot · {copilot.data.model}</span>{" "}
                    <span className="text-paper-faint">
                      (deterministic technical read, not advice)
                    </span>
                  </p>
                  <ul className="mt-1.5 space-y-1">
                    {copilot.data.rationale.slice(0, 2).map((line) => (
                      <li key={line} className="text-2xs leading-relaxed text-paper-faint">
                        · {line}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1.5 text-2xs text-warn/80">{copilot.data.invalidation}</p>
                </div>
              </div>
            </div>
          ) : null}
        </section>

        {/* Ticket */}
        <section className="panel order-2 flex flex-col xl:order-3 xl:sticky xl:top-20 xl:col-start-3 xl:row-start-1 xl:self-start">
          <div className="border-b border-line-soft px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-paper">Contract ticket</h2>
              <Badge tone="warn">Paper</Badge>
            </div>
            <p className="mt-0.5 text-3xs text-paper-faint">
              {activeAsset?.name ?? symbol} · {DURATIONS.find((d) => d.seconds === duration)?.label} expiry
            </p>
          </div>

          <div className="space-y-4 p-4">
            <div>
              <p className="label mb-1.5">Duration</p>
              <div className="grid grid-cols-5 gap-1 rounded-lg border border-line-soft bg-obsidian-900/60 p-1">
                {DURATIONS.map((option) => (
                  <button
                    key={option.seconds}
                    type="button"
                    onClick={() => setDuration(option.seconds)}
                    className={cn(
                      "rounded-md py-1.5 text-2xs transition",
                      duration === option.seconds
                        ? "bg-electric-500/20 text-electric-100 shadow-[inset_0_0_0_1px_rgba(46,123,255,0.4)]"
                        : "text-paper-faint hover:text-paper-muted",
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <p className="label">Stake</p>
                <p className="text-3xs text-paper-faint">
                  min {money(quote.data?.min_stake ?? 10)} · max {money(quote.data?.max_stake ?? 2000)}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => adjustStake(-25)}
                  className="rounded-lg border border-line-strong p-2 text-paper-muted transition hover:text-paper"
                  aria-label="Decrease stake"
                >
                  <Minus className="h-3.5 w-3.5" aria-hidden />
                </button>
                <div className="relative flex-1">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-paper-faint">$</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    min={quote.data?.min_stake ?? 10}
                    max={quote.data?.max_stake ?? 2000}
                    value={stake}
                    onChange={(event) => setStake(Number(event.target.value))}
                    aria-label="Stake amount"
                    className="num w-full rounded-lg border border-line bg-obsidian-900 py-2 pl-7 pr-2 text-center text-sm text-paper outline-none transition focus:border-electric-500/60"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => adjustStake(25)}
                  className="rounded-lg border border-line-strong p-2 text-paper-muted transition hover:text-paper"
                  aria-label="Increase stake"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
              <div className="mt-1.5 flex gap-1">
                {[50, 100, 250, 500].map((amount) => (
                  <button
                    key={amount}
                    type="button"
                    onClick={() => setStake(amount)}
                    className="flex-1 rounded border border-line-soft py-1 text-3xs text-paper-faint transition hover:border-line-strong hover:text-paper-muted"
                  >
                    ${amount}
                  </button>
                ))}
              </div>
            </div>

            <dl className="space-y-1.5 rounded-lg border border-line-soft bg-obsidian-900/60 p-3">
              <div className="flex items-center justify-between text-2xs">
                <dt className="text-paper-faint">Payout if correct</dt>
                <dd className="num text-emerald-300">{payout.toFixed(0)}%</dd>
              </div>
              <div className="flex items-center justify-between text-2xs">
                <dt className="text-paper-faint">Profit if correct</dt>
                <dd className="num text-paper">{money(potentialReturn)}</dd>
              </div>
              <div className="flex items-center justify-between text-2xs">
                <dt className="text-paper-faint">Returned if correct</dt>
                <dd className="num text-paper">{money(stake + potentialReturn)}</dd>
              </div>
              <div className="flex items-center justify-between text-2xs">
                <dt className="text-paper-faint">Loss if wrong</dt>
                <dd className="num text-loss">-{money(stake)}</dd>
              </div>
              <div className="flex items-center justify-between text-2xs">
                <dt className="text-paper-faint">Entry price</dt>
                <dd className="num text-paper">{fmtPrice(livePrice)}</dd>
              </div>
              <div className="flex items-center justify-between text-2xs">
                <dt className="text-paper-faint">Expiry</dt>
                <dd className="num text-paper">
                  {new Date(quote.data?.expires_at ?? Date.now()).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </dd>
              </div>
            </dl>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  setDirection("call");
                  setConfirmOpen(true);
                }}
                className="group flex flex-col items-center rounded-xl border border-emerald-500/40 bg-emerald-500/10 py-3 transition hover:bg-emerald-500/20"
              >
                <ArrowUpRight className="h-4 w-4 text-emerald-300" aria-hidden />
                <span className="mt-1 text-xs font-medium uppercase tracking-label text-emerald-200">Call</span>
                <span className="num text-3xs text-emerald-300/70">+{payout.toFixed(0)}%</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setDirection("put");
                  setConfirmOpen(true);
                }}
                className="group flex flex-col items-center rounded-xl border border-loss/40 bg-loss/10 py-3 transition hover:bg-loss/20"
              >
                <ArrowDownRight className="h-4 w-4 text-loss" aria-hidden />
                <span className="mt-1 text-xs font-medium uppercase tracking-label text-loss">Put</span>
                <span className="num text-3xs text-loss/70">+{payout.toFixed(0)}%</span>
              </button>
            </div>

            {lastRejection ? (
              <div className="rounded-lg border border-loss/30 bg-loss/[0.07] p-2.5">
                <p className="flex items-center gap-1.5 text-2xs font-medium text-loss">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> Rejected by the risk engine
                </p>
                <p className="mt-1 text-3xs leading-relaxed text-paper-muted">{lastRejection.reason}</p>
                {lastRejection.rules.length ? (
                  <ul className="mt-1.5 space-y-0.5">
                    {lastRejection.rules.slice(0, 3).map((rule) => (
                      <li key={rule} className="text-3xs text-paper-faint">
                        · {rule}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            <p className="flex items-start gap-1.5 text-3xs leading-relaxed text-paper-faint">
              <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
              Simulated contract on {quote.data?.price_source ?? "simulated"} prices. Stake is held for
              the contract term. A losing contract returns nothing.
            </p>
          </div>
        </section>

      <section className="panel order-4 xl:col-span-2 xl:col-start-2 xl:row-start-2">
        <div className="flex items-center justify-between border-b border-line-soft px-4 py-2.5">
          <div className="flex gap-1" role="tablist" aria-label="Contracts">
            {[
              ["open", `Open (${openContracts.length})`],
              ["history", `Settled (${settledContracts.length})`],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={sheetTab === key}
                onClick={() => setSheetTab(key as "open" | "history")}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-2xs transition",
                  sheetTab === key ? "bg-electric-500/15 text-electric-200" : "text-paper-faint hover:text-paper-muted",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {summary ? (
            <div className="hidden items-center gap-4 text-2xs sm:flex">
              <span className="text-paper-faint">
                Win rate <span className="num text-paper">{summary.win_rate_pct ?? "—"}%</span>
              </span>
              <span className="text-paper-faint">
                Net{" "}
                <span className={cn("num", summary.net_pnl >= 0 ? "text-gain" : "text-loss")}>
                  {money(summary.net_pnl)}
                </span>
              </span>
              <span className="text-paper-faint">
                Staked <span className="num text-paper">{money(summary.staked_total)}</span>
              </span>
            </div>
          ) : null}
        </div>

        {sheetTab === "open" ? (
          openContracts.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
              <Timer className="h-6 w-6 text-paper-faint" aria-hidden />
              <p className="mt-2 text-xs text-paper-muted">No open contracts</p>
              <p className="mt-1 max-w-sm text-3xs text-paper-faint">
                Pick a direction above. The stake is held until expiry and then settled automatically
                against the price at that moment.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-line-soft">
              {openContracts.map((contract) => (
                <li key={contract.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-lg border",
                        contract.direction === "call"
                          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                          : "border-loss/40 bg-loss/10 text-loss",
                      )}
                    >
                      {contract.direction === "call" ? (
                        <ArrowUpRight className="h-4 w-4" aria-hidden />
                      ) : (
                        <ArrowDownRight className="h-4 w-4" aria-hidden />
                      )}
                    </span>
                    <div>
                      <p className="font-mono text-xs text-paper">{contract.symbol}</p>
                      <p className="text-3xs text-paper-faint">
                        {contract.direction.toUpperCase()} · {money(contract.stake)} · {contract.payout_pct}% ·{" "}
                        {contract.duration_seconds / 60}m
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-3xs text-paper-faint">Entry</p>
                      <p className="num text-xs text-paper">{fmtPrice(contract.entry_price)}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-3xs text-paper-faint">Expires in</p>
                      <ContractCountdown expiresAt={contract.expires_at} />
                    </div>
                    <Badge tone="warn">Open</Badge>
                  </div>
                </li>
              ))}
            </ul>
          )
        ) : settledContracts.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-paper-faint">No settled contracts yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left">
              <thead>
                <tr className="border-b border-line-soft text-3xs uppercase tracking-label text-paper-faint">
                  <th className="px-4 py-2 font-normal">Contract</th>
                  <th className="px-4 py-2 font-normal">Direction</th>
                  <th className="px-4 py-2 text-right font-normal">Stake</th>
                  <th className="px-4 py-2 text-right font-normal">Entry → exit</th>
                  <th className="px-4 py-2 text-right font-normal">Net</th>
                  <th className="px-4 py-2 text-right font-normal">Result</th>
                  <th className="px-4 py-2 text-right font-normal">Record</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {settledContracts.map((contract) => (
                  <tr key={contract.id} className="text-xs hover:bg-obsidian-800/40">
                    <td className="px-4 py-2.5">
                      <p className="font-mono text-paper">{contract.symbol}</p>
                      <p className="text-3xs text-paper-faint">
                        {new Date(contract.opened_at).toLocaleString([], {
                          month: "short",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={contract.direction === "call" ? "text-emerald-300" : "text-loss"}>
                        {contract.direction.toUpperCase()}
                      </span>
                    </td>
                    <td className="num px-4 py-2.5 text-right text-paper">{money(contract.stake)}</td>
                    <td className="num px-4 py-2.5 text-right text-paper-muted">
                      {fmtPrice(contract.entry_price)} → {contract.exit_price ? fmtPrice(contract.exit_price) : "—"}
                    </td>
                    <td className={cn("num px-4 py-2.5 text-right", contract.net_pnl >= 0 ? "text-gain" : "text-loss")}>
                      {money(contract.net_pnl)}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <StatusPill status={contract.status} />
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => setDetailContract(contract)}
                        className="text-3xs text-electric-300 underline decoration-electric-500/40 underline-offset-2 hover:text-electric-200"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title={`${direction === "call" ? "Call" : "Put"} ${symbol} for ${DURATIONS.find((d) => d.seconds === duration)?.label}`}
        description="Simulated fixed-odds contract. The risk engine runs before the contract is opened and can reject it."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant={direction === "call" ? "success" : "danger"} loading={busy} onClick={submit}>
              {direction === "call" ? "Confirm call" : "Confirm put"}
            </Button>
          </>
        }
      >
        <dl className="space-y-2 text-xs">
          {[
            ["Stake (max loss)", money(stake)],
            ["Payout if correct", `${payout.toFixed(0)}% · ${money(potentialReturn)} profit`],
            ["Entry price", fmtPrice(livePrice)],
            ["Expiry", new Date(Date.now() + duration * 1000).toLocaleTimeString()],
            ["Data source", `${quote.data?.price_source ?? "simulated"}${quote.data?.is_demo ? " (demo)" : ""}`],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between border-b border-line-soft pb-2">
              <dt className="text-paper-faint">{label}</dt>
              <dd className="num text-paper">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 flex items-start gap-1.5 text-3xs leading-relaxed text-paper-faint">
          <ShieldCheck className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" aria-hidden />
          Checks include kill switches, data freshness, position size, exposure, daily loss, drawdown
          and your demo execution allowance.
        </p>
      </Dialog>

      <Dialog
        open={Boolean(detailContract)}
        onClose={() => setDetailContract(null)}
        title={detailContract ? `${detailContract.symbol} ${detailContract.direction.toUpperCase()}` : "Contract"}
        description="Immutable record of this simulated contract, including the risk checks that ran."
        wide
      >
        {detailContract ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ["Stake", money(detailContract.stake)],
                ["Payout", `${detailContract.payout_pct}%`],
                ["Entry", fmtPrice(detailContract.entry_price)],
                ["Exit", detailContract.exit_price ? fmtPrice(detailContract.exit_price) : "—"],
                ["Net P&L", money(detailContract.net_pnl)],
                ["Status", detailContract.status],
                ["Duration", `${detailContract.duration_seconds / 60}m`],
                ["Price source", detailContract.price_source],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-line-soft bg-obsidian-900/60 px-2.5 py-2">
                  <p className="text-3xs uppercase tracking-label text-paper-faint">{label}</p>
                  <p className="num mt-0.5 text-xs text-paper">{value}</p>
                </div>
              ))}
            </div>
            <div>
              <p className="label mb-1.5">Risk checks</p>
              <div className="flex flex-wrap gap-1">
                {(detailContract.risk.checks_passed ?? []).map((code) => (
                  <span
                    key={code}
                    className="rounded border border-emerald-500/25 bg-emerald-500/[0.08] px-1.5 py-0.5 font-mono text-3xs text-emerald-300"
                  >
                    {code}
                  </span>
                ))}
                {(detailContract.risk.checks_failed ?? []).map((code) => (
                  <span
                    key={code}
                    className="rounded border border-loss/30 bg-loss/10 px-1.5 py-0.5 font-mono text-3xs text-loss"
                  >
                    {code}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <p className="label mb-1.5">Entry reason</p>
              <p className="text-xs text-paper-muted">{detailContract.entry_reason || "—"}</p>
            </div>
            {detailContract.rejection_reason ? (
              <div className="rounded-lg border border-loss/30 bg-loss/[0.07] p-3">
                <p className="text-2xs text-loss">Rejected: {detailContract.rejection_reason}</p>
              </div>
            ) : null}
            <p className="text-3xs leading-relaxed text-paper-faint">
              Opened {new Date(detailContract.opened_at).toLocaleString()} ·{" "}
              {detailContract.settled_at
                ? `Settled ${new Date(detailContract.settled_at).toLocaleString()}`
                : `Expires ${new Date(detailContract.expires_at).toLocaleString()}`}
              . Simulated execution — no real funds moved.
            </p>
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}
