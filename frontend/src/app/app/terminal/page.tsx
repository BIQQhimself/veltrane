"use client";

import * as React from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  CandlestickChart,
  Clock,
  Crosshair,
  Eraser,
  Info,
  LineChart,
  Minus,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/hooks";
import { byAssetClass, CLASS_LABEL } from "@/lib/assets";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import {
  CandleChart,
  type Candle,
  type ChartMode,
  type Drawing,
  type DrawingTool,
} from "@/components/charts/candles";
import { RiskBudgetStrip } from "@/components/app/risk-budget";
import { PageHeader } from "@/components/ui/panel";
import { AccountChip, PositionsDock } from "@/components/terminal/account-chip";
import { InstrumentBar, Watchlist } from "@/components/terminal/instrument-bar";
import { TradeButtons } from "@/components/terminal/trade-buttons";
import { useFavourites } from "@/lib/favourites";
import { DerivTerminal } from "@/components/app/deriv-terminal";
import type { RiskBudget } from "@/lib/risk-budget";
import type {
  BinaryAsset,
  BinaryContract,
  BinaryQuote,
  BinarySummary,
  CopilotRead,
  CfdPosition,
  Connection,
} from "@/lib/types";

const DURATIONS = [
  { seconds: 60, label: "1m" },
  { seconds: 300, label: "5m" },
  { seconds: 900, label: "15m" },
  { seconds: 1800, label: "30m" },
  { seconds: 3600, label: "1h" },
];

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];



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

export default function TerminalPage() {
  const toast = useToast();
  const [assetClass, setAssetClass] = React.useState<string>("all");
  const [query, setQuery] = React.useState("");
  const [symbol, setSymbol] = React.useState("BTC/USDT");
  const [deepLinkHandled, setDeepLinkHandled] = React.useState(false);
  const [timeframe, setTimeframe] = React.useState<Timeframe>("15m");
  const [duration, setDuration] = React.useState(300);
  const [direction, setDirection] = React.useState<"call" | "put">("call");
  const [stake, setStake] = React.useState(100);
  const [busy, setBusy] = React.useState(false);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [detailContract, setDetailContract] = React.useState<BinaryContract | null>(null);
  const [sheetTab, setSheetTab] = React.useState<"open" | "history">("open");
  const [lastRejection, setLastRejection] = React.useState<{ reason: string; rules: string[] } | null>(null);
  const [chartMode, setChartMode] = React.useState<ChartMode>("candles");
  const [showEma, setShowEma] = React.useState(true);
  const [showVwap, setShowVwap] = React.useState(false);
  const [showRsi, setShowRsi] = React.useState(false);
  const [tool, setTool] = React.useState<DrawingTool>("none");
  const [drawings, setDrawings] = React.useState<Drawing[]>([]);
  const [assetPickerOpen, setAssetPickerOpen] = React.useState(false);
  const [ticketTab, setTicketTab] = React.useState<"fixed" | "cfd" | "deriv">("fixed");
  const [cfdSide, setCfdSide] = React.useState<"buy" | "sell">("buy");
  const [cfdQty, setCfdQty] = React.useState("0.01");
  const [cfdSl, setCfdSl] = React.useState("");
  const [cfdTp, setCfdTp] = React.useState("");
  const [cfdBusy, setCfdBusy] = React.useState(false);

  const assets = useApi<{ assets: BinaryAsset[] }>((signal) => api("/binary/assets", { signal }));
  const contracts = useApi<{ contracts: BinaryContract[]; summary: BinarySummary }>((signal) =>
    api("/binary/contracts", { signal, query: { limit: 60 } }),
  );
  const candles = useApi<{ candles: Candle[]; meta: { source: string; is_demo: boolean } }>((signal) =>
    api(`/markets/candles/${encodeURIComponent(symbol)}`, { signal, query: { timeframe, limit: 160 } }),
    [symbol, timeframe],
  );
  const positions = useApi<{ positions: CfdPosition[] }>((signal) =>
    api("/positions", { signal, query: { status: "open" } }),
  );
  const overview = useApi<{ equity: { paper_equity_usd: number } }>((signal) =>
    api("/portfolio/overview", { signal }),
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
  const riskBudget = useApi<RiskBudget>((signal) => api("/trading/risk-budget", { signal }));
  const connections = useApi<{ connections: Connection[] }>((signal) => api("/connections", { signal }));
  const connectionList = React.useMemo(() => connections.data?.connections ?? [], [connections.data]);

  const assetList = React.useMemo(() => assets.data?.assets ?? [], [assets.data]);
  // Crypto leads the list: it is the first market with live trading enabled.
  const filtered = React.useMemo(() => {
    const ordered = [...assetList].sort(byAssetClass);
    return ordered.filter((asset) => {
      const classOk = assetClass === "all" || asset.asset_class === assetClass;
      const queryOk =
        !query ||
        asset.symbol.toLowerCase().includes(query.toLowerCase()) ||
        asset.name.toLowerCase().includes(query.toLowerCase());
      return classOk && queryOk;
    });
  }, [assetList, assetClass, query]);

  const { favourites, toggle: toggleFavourite } = useFavourites();

  const stepInstrument = React.useCallback(
    (direction: -1 | 1) => {
      if (!assetList.length) return;
      const index = assetList.findIndex((asset) => asset.symbol === symbol);
      const next = (index + direction + assetList.length) % assetList.length;
      const candidate = assetList[next];
      if (candidate) setSymbol(candidate.symbol);
    },
    [assetList, symbol, setSymbol],
  );

  const activeAsset = assetList.find((asset) => asset.symbol === symbol);
  const openContracts = (contracts.data?.contracts ?? []).filter((c) => c.status === "open");
  const settledContracts = (contracts.data?.contracts ?? []).filter((c) => c.status !== "open");
  const summary = contracts.data?.summary;
  const payout = quote.data?.payout_pct ?? Number(activeAsset?.payouts?.[String(duration)] ?? 0);
  const potentialReturn = (stake * payout) / 100;
  const quoteMatchesSymbol = quote.data?.symbol === symbol;
  const livePrice = (quoteMatchesSymbol ? quote.data?.price : undefined) ?? candles.data?.candles.at(-1)?.close ?? 0;
  const isDemoFeed = candles.data?.meta?.is_demo ?? true;
  const firstClose = candles.data?.candles[0]?.close;
  const changePct = firstClose && livePrice ? ((livePrice - firstClose) / firstClose) * 100 : 0;

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

  React.useEffect(() => {
    const timer = setInterval(() => riskBudget.refetch(), 20_000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Chart annotations are per instrument and timeframe, kept on the device only.
  const drawingKey = `veltrane:drawings:${symbol}:${timeframe}`;
  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(drawingKey);
      setDrawings(raw ? (JSON.parse(raw) as Drawing[]) : []);
    } catch {
      setDrawings([]);
    }
  }, [drawingKey]);

  const persistDrawings = (next: Drawing[]) => {
    setDrawings(next);
    try {
      window.localStorage.setItem(drawingKey, JSON.stringify(next));
    } catch {
      // Storage can be unavailable in private mode; annotations simply do not persist.
    }
  };

  const addDrawing = (drawing: Drawing) => {
    persistDrawings([...drawings, drawing].slice(-24));
    setTool("none");
  };

  const openPositions = positions.data?.positions ?? [];
  // The risk engine caps a single order at 10% of equity; surface that limit in the
  // ticket so a size the engine will reject is obvious before it is submitted.
  const equity = overview.data?.equity.paper_equity_usd ?? 0;
  const maxNotional = equity * 0.1;
  const maxQty = livePrice > 0 ? maxNotional / livePrice : 0;

  const positionPnl = (position: CfdPosition) => {
    if (position.symbol === symbol && livePrice) {
      const direction = position.side === "sell" ? -1 : 1;
      return (livePrice - position.avg_entry_price) * position.quantity * direction;
    }
    return position.unrealized_pnl ?? 0;
  };

  const submitCfd = async () => {
    const quantity = Number(cfdQty);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      toast.error("Invalid size", "Enter a quantity greater than zero.");
      return;
    }
    setCfdBusy(true);
    try {
      const result = await api<{ fill: { price: number } | null; order: { status: string } }>("/orders", {
        method: "POST",
        body: {
          symbol,
          side: cfdSide,
          quantity,
          order_type: "market",
          mode: "paper",
          stop_loss: cfdSl ? Number(cfdSl) : null,
          take_profit: cfdTp ? Number(cfdTp) : null,
          idempotency_key: `cfd-${symbol}-${cfdSide}-${Date.now()}`,
          reason: `CFD ${cfdSide} from terminal`,
        },
      });
      toast.success(
        "Position opened",
        `${cfdSide.toUpperCase()} ${quantity} ${symbol} at ${fmtPrice(result.fill?.price ?? livePrice)} · paper.`,
      );
      positions.refetch();
      setCfdSl("");
      setCfdTp("");
    } catch (error) {
      setLastRejection({ reason: errorMessage(error), rules: [] });
      toast.error("Order rejected", errorMessage(error));
    } finally {
      setCfdBusy(false);
    }
  };

  const closeCfd = async (position: CfdPosition) => {
    try {
      await api(`/positions/${position.id}/close`, {
        method: "POST",
        body: { reason: "Manual close from terminal" },
      });
      toast.success("Position closed", `${position.symbol} ${position.side.toUpperCase()} at market.`);
      positions.refetch();
      contracts.refetch();
    } catch (error) {
      toast.error("Could not close position", errorMessage(error));
    }
  };

  const bias = copilot.data?.bias ?? "neutral";

  return (
    <div className="space-y-3 pb-24 xl:pb-0">
      <PageHeader
        eyebrow="Trade"
        title="Trading terminal"
        badge={
          <>
            <Badge tone="info">Fixed-odds</Badge>
            <Badge tone="warn">Simulated</Badge>
          </>
        }
        description="Every contract passes the independent risk engine before it opens. Expiries are one minute or longer on the platform book; a venue offers whatever it publishes."
        action={
          <>
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
            {openContracts.length + openPositions.length} open ·{" "}
            {summary?.open_stake ? money(summary.open_stake) : money(0)} staked
          </span>
          </>
        }
      />

      <InstrumentBar
        symbol={symbol}
        asset={activeAsset}
        price={livePrice}
        changePct={changePct}
        isDemoFeed={isDemoFeed}
        favourite={favourites.includes(symbol)}
        onToggleFavourite={() => toggleFavourite(symbol)}
        onOpenPicker={() => setAssetPickerOpen(true)}
        onStep={stepInstrument}
      >
        <AccountChip
          connections={connectionList}
          balance={equity}
          simulated
          equityLabel="Paper equity"
        />
      </InstrumentBar>

      <Watchlist
        assets={assetList}
        favourites={favourites}
        active={symbol}
        onSelect={setSymbol}
        onToggleFavourite={toggleFavourite}
        loading={assets.loading}
      />

      <RiskBudgetStrip budget={riskBudget.data} />

      {/* Mobile: the two decisions stay within thumb reach no matter how far the chart scrolls. */}
      <div className="fixed inset-x-0 bottom-[64px] z-30 border-t border-line-soft bg-obsidian-900/95 px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur-xl xl:hidden">
        <div className="mx-auto flex max-w-md items-center gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-2xs font-medium text-paper">{symbol}</p>
            <p className="num text-3xs text-paper-faint">
              {money(stake)} · {DURATIONS.find((option) => option.seconds === duration)?.label ?? "1m"} · +
              {payout.toFixed(0)}%
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setDirection("call");
              setConfirmOpen(true);
            }}
            className="trade-call flex-row gap-1.5 px-4 py-2.5"
          >
            <ArrowUpRight className="h-4 w-4" aria-hidden />
            <span className="text-xs font-semibold uppercase tracking-label">Call</span>
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setDirection("put");
              setConfirmOpen(true);
            }}
            className="trade-put flex-row gap-1.5 px-4 py-2.5"
          >
            <ArrowDownRight className="h-4 w-4" aria-hidden />
            <span className="text-xs font-semibold uppercase tracking-label">Put</span>
          </button>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_336px]">
        {/* Chart + positions dock */}
        <div className="order-1 min-w-0 space-y-3">
          <section className="panel">
            <div className="border-b border-line-soft">
              <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-2">
                <p className="text-2xs text-paper-faint">
                  <span className="font-mono text-paper">{symbol}</span> chart ·{" "}
                  {DURATIONS.find((d) => d.seconds === duration)?.label} expiry
                </p>
                <div className="flex shrink-0 items-center gap-1 rounded-lg border border-line-soft bg-obsidian-900/60 p-0.5">
                  {TIMEFRAMES.map((tf) => (
                    <button
                      key={tf}
                      type="button"
                      onClick={() => setTimeframe(tf)}
                      className={cn(
                        "rounded px-1.5 py-1 text-3xs transition",
                        timeframe === tf ? "bg-gold-400/15 text-gold-300" : "text-paper-faint hover:text-paper-muted",
                      )}
                    >
                      {tf}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-between gap-2 border-t border-line-soft/60 px-3 py-1.5">
                <div className="flex items-center gap-1">
                  <div className="flex items-center gap-0.5 rounded-md border border-line-soft p-0.5" role="group" aria-label="Chart type">
                    <button
                      type="button"
                      onClick={() => setChartMode("candles")}
                      aria-pressed={chartMode === "candles"}
                      title="Candlesticks"
                      className={cn(
                        "rounded p-1 transition",
                        chartMode === "candles" ? "bg-ink-750 text-paper" : "text-paper-faint hover:text-paper-muted",
                      )}
                    >
                      <CandlestickChart className="h-3.5 w-3.5" aria-hidden />
                      <span className="sr-only">Candlesticks</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setChartMode("line")}
                      aria-pressed={chartMode === "line"}
                      title="Line"
                      className={cn(
                        "rounded p-1 transition",
                        chartMode === "line" ? "bg-ink-750 text-paper" : "text-paper-faint hover:text-paper-muted",
                      )}
                    >
                      <LineChart className="h-3.5 w-3.5" aria-hidden />
                      <span className="sr-only">Line</span>
                    </button>
                  </div>
                  {([
                    ["EMA 21", showEma, () => setShowEma((value) => !value)],
                    ["VWAP", showVwap, () => setShowVwap((value) => !value)],
                    ["RSI 14", showRsi, () => setShowRsi((value) => !value)],
                  ] as const).map(([label, active, toggle]) => (
                    <button
                      key={label}
                      type="button"
                      onClick={toggle}
                      aria-pressed={active}
                      className={cn(
                        "rounded-md border px-2 py-1 text-3xs transition",
                        active
                          ? "border-gold-400/40 bg-gold-400/10 text-gold-300"
                          : "border-line-soft text-paper-faint hover:text-paper-muted",
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setTool(tool === "hline" ? "none" : "hline")}
                    aria-pressed={tool === "hline"}
                    title="Horizontal line"
                    className={cn(
                      "rounded-md border p-1 transition",
                      tool === "hline" ? "border-gold-400/40 bg-gold-400/10 text-gold-300" : "border-line-soft text-paper-faint hover:text-paper-muted",
                    )}
                  >
                    <Crosshair className="h-3.5 w-3.5" aria-hidden />
                    <span className="sr-only">Draw horizontal line</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setTool(tool === "trend" ? "none" : "trend")}
                    aria-pressed={tool === "trend"}
                    title="Trend line"
                    className={cn(
                      "rounded-md border p-1 transition",
                      tool === "trend" ? "border-gold-400/40 bg-gold-400/10 text-gold-300" : "border-line-soft text-paper-faint hover:text-paper-muted",
                    )}
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden />
                    <span className="sr-only">Draw trend line</span>
                  </button>
                  {drawings.length ? (
                    <button
                      type="button"
                      onClick={() => persistDrawings([])}
                      title="Clear drawings"
                      className="rounded-md border border-line-soft p-1 text-paper-faint transition hover:text-loss"
                    >
                      <Eraser className="h-3.5 w-3.5" aria-hidden />
                      <span className="sr-only">Clear drawings</span>
                    </button>
                  ) : null}
                  {tool !== "none" ? (
                    <button
                      type="button"
                      onClick={() => setTool("none")}
                      className="rounded-md border border-line-soft p-1 text-paper-faint transition hover:text-paper"
                      title="Stop drawing"
                    >
                      <X className="h-3.5 w-3.5" aria-hidden />
                      <span className="sr-only">Stop drawing</span>
                    </button>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="relative">
              {candles.loading && !candles.data ? (
                <div className="shimmer m-4 h-[300px] rounded-lg" />
              ) : (
                <CandleChart
                  candles={candles.data?.candles ?? []}
                  height={360}
                  mode={chartMode}
                  showEma={showEma}
                  showVwap={showVwap}
                  showRsi={showRsi}
                  showCrosshair
                  drawings={drawings}
                  tool={tool}
                  onDraw={addDrawing}
                  livePrice={livePrice}
                  entryPrice={
                    openContracts.find((c) => c.symbol === symbol)?.entry_price ??
                    openPositions.find((p) => p.symbol === symbol)?.avg_entry_price ??
                    null
                  }
                  entryDirection={
                    openContracts.find((c) => c.symbol === symbol)?.direction ??
                    (openPositions.find((p) => p.symbol === symbol)?.side as "buy" | "sell" | undefined) ??
                    null
                  }
                  stopLoss={openPositions.find((p) => p.symbol === symbol)?.stop_loss ?? null}
                  takeProfit={openPositions.find((p) => p.symbol === symbol)?.take_profit ?? null}
                  ariaLabel={`${symbol} price chart`}
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
                  <Bot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-champagne-300" aria-hidden />
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

          <PositionsDock
            tab={sheetTab}
            onTab={setSheetTab}
            open={openContracts}
            settled={settledContracts}
            summary={summary ?? undefined}
            onOpenContract={setDetailContract}
            loading={contracts.loading}
          />
        </div>

        {/* Ticket */}
        <section className="panel order-2 flex flex-col xl:sticky xl:top-20 xl:self-start">
          <div className="border-b border-line-soft px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-paper">Trade ticket</h2>
              <Badge tone="warn">
                {ticketTab === "deriv" ? "Venue" : ticketTab === "cfd" ? "Sim" : "Paper"}
              </Badge>
            </div>
            <p className="mt-0.5 text-3xs text-paper-faint">
              {activeAsset?.name ?? symbol} ·{" "}
              {ticketTab === "fixed"
                ? `${DURATIONS.find((d) => d.seconds === duration)?.label} expiry`
                : ticketTab === "deriv"
                  ? "fixed-odds contract on your own Deriv account"
                  : "market execution, open-ended"}
            </p>
            <div className="mt-2.5 grid grid-cols-3 gap-1 rounded-lg border border-line-soft bg-obsidian-900/60 p-0.5">
              {(
                [
                  ["fixed", "Fixed-time"],
                  ["cfd", "CFD"],
                  ["deriv", "Deriv"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTicketTab(key)}
                  aria-pressed={ticketTab === key}
                  className={cn(
                    "rounded-md py-1.5 text-2xs transition",
                    ticketTab === key
                      ? "bg-ink-750 text-paper shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
                      : "text-paper-faint hover:text-paper-muted",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {ticketTab === "deriv" ? (
            <DerivTerminal connections={connectionList} />
          ) : ticketTab === "cfd" ? (
            <div className="space-y-4 p-4">
              <div>
                <p className="label mb-1.5">Size ({activeAsset?.symbol.split("/")[0] ?? "units"})</p>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setCfdQty((value) => String(Math.max(0.01, Number(value) / 2)))}
                    className="rounded-lg border border-line-strong p-2 text-paper-muted transition hover:text-paper"
                    aria-label="Halve size"
                  >
                    <Minus className="h-3.5 w-3.5" aria-hidden />
                  </button>
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0.01}
                    step={0.01}
                    value={cfdQty}
                    onChange={(event) => setCfdQty(event.target.value)}
                    aria-label="Position size"
                    className="num w-full rounded-lg border border-line bg-obsidian-900 py-2 text-center text-sm text-paper outline-none transition focus:border-gold-400/60"
                  />
                  <button
                    type="button"
                    onClick={() => setCfdQty((value) => String(Math.round(Number(value) * 2 * 100) / 100))}
                    className="rounded-lg border border-line-strong p-2 text-paper-muted transition hover:text-paper"
                    aria-label="Double size"
                  >
                    <Plus className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between text-3xs text-paper-faint">
                <span>
                  Max ≈ {maxQty > 0 ? maxQty.toFixed(4) : "—"} ({money(maxNotional)} notional cap)
                </span>
                <button
                  type="button"
                  onClick={() => setCfdQty(maxQty > 0 ? (maxQty * 0.95).toFixed(4) : "0.01")}
                  className="rounded border border-line-soft px-1.5 py-0.5 transition hover:border-gold-400/40 hover:text-gold-300"
                >
                  Use max
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <label className="block">
                  <span className="label mb-1 block">Stop loss</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    value={cfdSl}
                    onChange={(event) => setCfdSl(event.target.value)}
                    placeholder={fmtPrice(livePrice * (cfdSide === "buy" ? 0.98 : 1.02))}
                    aria-label="Stop loss price"
                    className="num w-full rounded-lg border border-loss/30 bg-obsidian-900 px-2 py-2 text-xs text-paper outline-none transition focus:border-loss/70"
                  />
                </label>
                <label className="block">
                  <span className="label mb-1 block">Take profit</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    value={cfdTp}
                    onChange={(event) => setCfdTp(event.target.value)}
                    placeholder={fmtPrice(livePrice * (cfdSide === "buy" ? 1.02 : 0.98))}
                    aria-label="Take profit price"
                    className="num w-full rounded-lg border border-gain/30 bg-obsidian-900 px-2 py-2 text-xs text-paper outline-none transition focus:border-gain/70"
                  />
                </label>
              </div>

              <dl className="space-y-1.5 rounded-lg border border-line-soft bg-obsidian-900/60 p-3">
                <div className="flex items-center justify-between text-2xs">
                  <dt className="text-paper-faint">Entry (market)</dt>
                  <dd className="num text-paper">{fmtPrice(livePrice)}</dd>
                </div>
                <div className="flex items-center justify-between text-2xs">
                  <dt className="text-paper-faint">Notional</dt>
                  <dd className="num text-paper">{money(Number(cfdQty) * livePrice || 0)}</dd>
                </div>
                <div className="flex items-center justify-between text-2xs">
                  <dt className="text-paper-faint">Open positions</dt>
                  <dd className="num text-paper">{openPositions.length}</dd>
                </div>
              </dl>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setCfdSide("buy")}
                  aria-pressed={cfdSide === "buy"}
                  className={cn(
                    "flex flex-col items-center rounded-xl border py-3 transition",
                    cfdSide === "buy"
                      ? "border-gain bg-gain/20 text-gain shadow-[0_0_24px_-10px_rgba(0,224,122,0.8)]"
                      : "border-gain/30 bg-gain/5 text-gain/70 hover:bg-gain/10",
                  )}
                >
                  <ArrowUpRight className="h-4 w-4" aria-hidden />
                  <span className="mt-1 text-xs font-semibold uppercase tracking-label">Buy</span>
                  <span className="num text-3xs opacity-80">{fmtPrice(livePrice)}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setCfdSide("sell")}
                  aria-pressed={cfdSide === "sell"}
                  className={cn(
                    "flex flex-col items-center rounded-xl border py-3 transition",
                    cfdSide === "sell"
                      ? "border-loss bg-loss/20 text-loss shadow-[0_0_24px_-10px_rgba(255,59,82,0.8)]"
                      : "border-loss/30 bg-loss/5 text-loss/70 hover:bg-loss/10",
                  )}
                >
                  <ArrowDownRight className="h-4 w-4" aria-hidden />
                  <span className="mt-1 text-xs font-semibold uppercase tracking-label">Sell</span>
                  <span className="num text-3xs opacity-80">{fmtPrice(livePrice)}</span>
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

              <Button
                fullWidth
                variant={cfdSide === "buy" ? "success" : "danger"}
                loading={cfdBusy}
                onClick={submitCfd}
              >
                {cfdSide === "buy" ? "Buy" : "Sell"} {symbol}
              </Button>

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <p className="label">Open positions</p>
                  <button
                    type="button"
                    onClick={() => positions.refetch()}
                    className="text-3xs text-paper-faint transition hover:text-paper"
                  >
                    Refresh
                  </button>
                </div>
                {openPositions.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-line-soft px-3 py-4 text-center text-3xs text-paper-faint">
                    No open CFD positions.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {openPositions.map((position) => {
                      const pnl = positionPnl(position);
                      return (
                        <li
                          key={position.id}
                          className="rounded-lg border border-line-soft bg-obsidian-900/60 px-2.5 py-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-2xs text-paper">{position.symbol}</span>
                            <span
                              className={cn(
                                "rounded px-1 py-0.5 text-3xs font-semibold uppercase",
                                position.side === "buy" ? "bg-gain/15 text-gain" : "bg-loss/15 text-loss",
                              )}
                            >
                              {position.side}
                            </span>
                          </div>
                          <div className="mt-1 flex items-end justify-between gap-2">
                            <span className="text-3xs text-paper-faint">
                              {position.quantity} @ {fmtPrice(position.avg_entry_price)}
                            </span>
                            <span className={cn("num text-xs", pnl >= 0 ? "text-gain" : "text-loss")}>
                              {pnl >= 0 ? "+" : ""}
                              {money(pnl)}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => closeCfd(position)}
                            className="mt-1.5 w-full rounded border border-line-strong py-1 text-3xs text-paper-muted transition hover:border-loss/50 hover:text-loss"
                          >
                            Close position
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <p className="flex items-start gap-1.5 text-3xs leading-relaxed text-paper-faint">
                <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                Paper CFD on {quote.data?.price_source ?? "simulated"} prices. The independent risk
                engine validates size, exposure and stop placement before the order is accepted.
              </p>
            </div>
          ) : (
          <div className="space-y-4 p-4">
            {/* The payout is the number a fixed-odds trader reads first, so it leads. */}
            <div className="rounded-2xl border border-line-soft bg-gradient-to-b from-white/[0.055] to-transparent px-4 py-3">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="label">Payout if correct</p>
                  <p className="num mt-1 text-[32px] font-medium leading-none text-gain">+{payout.toFixed(0)}%</p>
                </div>
                <div className="text-right">
                  <p className="text-3xs text-paper-faint">You collect</p>
                  <p className="num text-sm text-paper">{money(stake + potentialReturn)}</p>
                  <p className="num text-3xs text-loss">-{money(stake)} if wrong</p>
                </div>
              </div>
            </div>

            <div>
              <p className="label mb-2">Expiry</p>
              <div className="grid grid-cols-5 gap-1.5">
                {DURATIONS.map((option) => (
                  <button
                    key={option.seconds}
                    type="button"
                    onClick={() => setDuration(option.seconds)}
                    aria-pressed={duration === option.seconds}
                    data-active={duration === option.seconds}
                    className="pick px-0 text-center"
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-baseline justify-between">
                <p className="label">Stake</p>
                <p className="text-3xs text-paper-faint">
                  {money(quote.data?.min_stake ?? 10)} – {money(quote.data?.max_stake ?? 2000)}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => adjustStake(-25)}
                  className="rounded-control border border-line-strong p-2.5 text-paper-muted transition hover:text-paper"
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
                    className="num h-10 w-full rounded-control border border-line-strong bg-obsidian-900 py-2 pl-7 pr-2 text-center text-sm text-paper outline-none transition focus:border-champagne-500/70"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => adjustStake(25)}
                  className="rounded-control border border-line-strong p-2.5 text-paper-muted transition hover:text-paper"
                  aria-label="Increase stake"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
              <div className="mt-1.5 grid grid-cols-4 gap-1.5">
                {[50, 100, 250, 500].map((amount) => (
                  <button
                    key={amount}
                    type="button"
                    onClick={() => setStake(amount)}
                    data-active={stake === amount}
                    className="pick px-0 text-center text-3xs"
                  >
                    ${amount}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between rounded-control border border-line-soft bg-obsidian-900/50 px-3 py-2 text-3xs text-paper-faint">
              <span>
                Entry <span className="num text-paper">{fmtPrice(livePrice)}</span>
              </span>
              <span>
                Expires{" "}
                <span className="num text-paper">
                  {new Date(quote.data?.expires_at ?? Date.now()).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
              </span>
            </div>

            <TradeButtons
              stake={stake}
              payoutPct={payout}
              durationLabel={DURATIONS.find((option) => option.seconds === duration)?.label ?? "1m"}
              busy={busy}
              onPick={(next) => {
                setDirection(next);
                setConfirmOpen(true);
              }}
            />

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
          )}
        </section>
      </div>

      <Dialog
        open={assetPickerOpen}
        onClose={() => setAssetPickerOpen(false)}
        title="Select instrument"
        description="Crypto, forex, equities and metals. Payouts are modelled per asset and duration."
        wide
      >
        <div className="space-y-3">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-paper-faint" aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search symbol or name"
              aria-label="Search instruments"
              autoFocus
              className="w-full rounded-lg border border-line bg-obsidian-900 py-2 pl-8 pr-2 text-xs text-paper outline-none transition focus:border-gold-400/60"
            />
          </label>
          <div className="flex flex-wrap gap-1">
            {["all", "crypto", "forex", "stock", "commodity"].map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setAssetClass(key)}
                className={cn(
                  "rounded px-2 py-1 text-3xs uppercase tracking-label transition",
                  assetClass === key ? "bg-gold-400/15 text-gold-300" : "text-paper-faint hover:text-paper-muted",
                )}
              >
                {key === "all" ? "All" : CLASS_LABEL[key]}
              </button>
            ))}
          </div>
          <ul className="max-h-[52vh] divide-y divide-line-soft overflow-y-auto rounded-lg border border-line-soft">
            {filtered.length === 0 ? (
              <li className="px-3 py-6 text-center text-xs text-paper-faint">No instruments match that search.</li>
            ) : (
              filtered.map((asset) => {
                const active = asset.symbol === symbol;
                return (
                  <li key={asset.symbol}>
                    <button
                      type="button"
                      onClick={() => {
                        setSymbol(asset.symbol);
                        setAssetPickerOpen(false);
                      }}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition",
                        active ? "bg-gold-400/[0.08]" : "hover:bg-ink-800/70",
                      )}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-mono text-xs text-paper">{asset.symbol}</span>
                        <span className="block truncate text-3xs text-paper-faint">
                          {asset.name} · {CLASS_LABEL[asset.asset_class] ?? asset.asset_class}
                        </span>
                      </span>
                      <span className="num shrink-0 text-2xs text-gain">
                        {Number(asset.payouts?.[String(duration)] ?? 0)}%
                      </span>
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      </Dialog>

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
            ["Data source", quote.data?.is_demo ? "Simulated demo feed" : (quote.data?.price_source ?? "Simulated feed")],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between border-b border-line-soft pb-2">
              <dt className="text-paper-faint">{label}</dt>
              <dd className="num text-paper">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 flex items-start gap-1.5 text-3xs leading-relaxed text-paper-faint">
          <ShieldCheck className="mt-0.5 h-3 w-3 shrink-0 text-gain" aria-hidden />
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
                    className="rounded border border-gain/25 bg-gain/[0.08] px-1.5 py-0.5 font-mono text-3xs text-gain"
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
      {/* Mobile one-tap ticket: the full ticket lives below the chart, this keeps the
          two directions reachable with a thumb while the chart is on screen. */}
      <div className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-30 flex items-center gap-2 border-t border-line bg-obsidian-950/95 px-3 py-2 backdrop-blur xl:hidden">
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-3xs text-paper-faint">{symbol}</p>
          <p className={cn("num text-sm", changePct >= 0 ? "text-gain" : "text-loss")}>
            {fmtPrice(livePrice)}{" "}
            <span className="text-3xs">
              {changePct >= 0 ? "▲" : "▼"} {Math.abs(changePct).toFixed(2)}%
            </span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setDirection("call");
            setTicketTab("fixed");
            setConfirmOpen(true);
          }}
          className="flex-1 rounded-lg bg-gain py-2.5 text-xs font-semibold uppercase tracking-label text-ink-950"
        >
          Up · +{payout.toFixed(0)}%
        </button>
        <button
          type="button"
          onClick={() => {
            setDirection("put");
            setTicketTab("fixed");
            setConfirmOpen(true);
          }}
          className="flex-1 rounded-lg bg-loss py-2.5 text-xs font-semibold uppercase tracking-label text-white"
        >
          Down · +{payout.toFixed(0)}%
        </button>
      </div>
    </div>
  );
}
