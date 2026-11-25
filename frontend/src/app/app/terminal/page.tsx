"use client";

import * as React from "react";
import { ArrowDownRight, ArrowUpRight, RefreshCw, ShieldAlert, X } from "lucide-react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { bps, dateTime, money, signedMoney, titleCase } from "@/lib/format";
import { Badge, DemoBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Tabs } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { TradeDetailDialog } from "@/components/app/trade-detail";
import type { Instrument, Order, PaperSession, Position, Trade, TradingState } from "@/lib/types";

type Ticker = { symbol: string; price: number; is_demo?: boolean; source?: string };
type OrderResponse = {
  idempotent_replay?: boolean;
  order: Order;
  risk_decision?: { decision: string; checks: Array<{ code: string; passed: boolean; message: string }> };
};

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `k-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function TerminalPage() {
  const toast = useToast();
  const { entitlements, platform } = useAuth();
  const state = useApi<TradingState>((signal) => api("/trading/state", { signal }));
  const instruments = useApi<{ instruments: Instrument[] }>((signal) => api("/markets/instruments", { signal }));
  const sessions = useApi<{ sessions: PaperSession[] }>((signal) => api("/paper-sessions", { signal }));
  const orders = useApi<{ orders: Order[] }>((signal) => api("/orders", { signal, query: { limit: 25 } }));
  const trades = useApi<{ trades: Trade[] }>((signal) => api("/trades", { signal, query: { limit: 25 } }));

  const [symbol, setSymbol] = React.useState("BTC/USDT");
  const [side, setSide] = React.useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = React.useState<"market" | "limit" | "stop" | "stop_limit">("market");
  const [quantity, setQuantity] = React.useState("0.01");
  const [price, setPrice] = React.useState("");
  const [stopLoss, setStopLoss] = React.useState("");
  const [takeProfit, setTakeProfit] = React.useState("");
  const [reason, setReason] = React.useState("Manual order from trading terminal");
  const [mode, setMode] = React.useState<"paper" | "live">("paper");
  const [sessionId, setSessionId] = React.useState("");
  const [idempotencyKey, setIdempotencyKey] = React.useState(newIdempotencyKey);
  const [busy, setBusy] = React.useState(false);
  const [lastDecision, setLastDecision] = React.useState<OrderResponse["risk_decision"] | null>(null);
  const [lastError, setLastError] = React.useState<string | null>(null);
  const [selectedTrade, setSelectedTrade] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState("positions");

  const ticker = useApi<Ticker>((signal) => api(`/markets/ticker/${encodeURIComponent(symbol)}`, { signal }), [symbol]);
  const liveEnabled = Boolean(platform?.live_trading_enabled) && Boolean(entitlements?.features?.live_trading);
  const killEngaged = Boolean(
    (state.data?.kill_switches as Record<string, { engaged?: boolean }> | undefined)?.org?.engaged,
  );

  React.useEffect(() => {
    const running = sessions.data?.sessions.find((item) => item.status === "running");
    if (running && !sessionId) setSessionId(running.id);
  }, [sessions.data, sessionId]);

  const qty = Number(quantity);
  const referencePrice = orderType === "market" ? ticker.data?.price ?? 0 : Number(price) || 0;
  const notional = Number.isFinite(qty * referencePrice) ? qty * referencePrice : 0;
  const openPositions = state.data?.open_positions ?? [];
  const sessionList = sessions.data?.sessions ?? [];

  async function submitOrder(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setLastError(null);
    setLastDecision(null);
    try {
      const result = await api<OrderResponse>("/orders", {
        method: "POST",
        body: {
          symbol,
          side,
          quantity: qty,
          order_type: orderType,
          price: orderType === "market" ? null : Number(price) || null,
          stop_price: orderType.startsWith("stop") ? Number(price) || null : null,
          stop_loss: stopLoss ? Number(stopLoss) : null,
          take_profit: takeProfit ? Number(takeProfit) : null,
          mode,
          paper_session_id: mode === "paper" ? sessionId || null : null,
          idempotency_key: idempotencyKey,
          reason,
        },
      });
      setLastDecision(result.risk_decision ?? null);
      if (result.order.status === "rejected") {
        toast.error("Rejected by the risk engine", result.order.rejection_reason ?? "See the checks below.");
      } else {
        toast.success(
          result.order.status === "filled" ? "Simulated fill recorded" : "Order accepted",
          `${side.toUpperCase()} ${quantity} ${symbol}${result.idempotent_replay ? " (idempotent replay)" : ""}`,
        );
      }
      setIdempotencyKey(newIdempotencyKey());
      orders.refetch();
      trades.refetch();
      state.refetch();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : errorMessage(error);
      setLastError(message);
      toast.error("Order not accepted", message);
    } finally {
      setBusy(false);
    }
  }

  async function closePosition(position: Position) {
    setBusy(true);
    try {
      const result = await api<{ trade: Trade | null }>(`/positions/${position.id}/close`, {
        method: "POST",
        body: { reason: "Manual close from terminal", note: "Closed by the trader in the terminal" },
      });
      toast.success("Position closed", result.trade ? `Net ${signedMoney(result.trade.net_pnl)}` : undefined);
      if (result.trade) setSelectedTrade(result.trade.id);
      state.refetch();
      trades.refetch();
      orders.refetch();
    } catch (error) {
      toast.error("Close failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function cancelOrder(order: Order) {
    setBusy(true);
    try {
      await api(`/orders/${order.id}/cancel`, { method: "POST" });
      toast.info("Order cancelled");
      orders.refetch();
    } catch (error) {
      toast.error("Cancel failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Execution"
        title="Trading terminal"
        description="Manual and strategy orders pass the same risk engine. Simulated fills are marked as such, and every rejection is stored with the rule that failed."
        action={
          <div className="flex items-center gap-2">
            <Badge tone={killEngaged ? "loss" : "gain"}>{killEngaged ? "Trading halted" : "Trading enabled"}</Badge>
            <Badge tone="info">{state.data?.data_source_mode ?? "demo"} data</Badge>
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          <Panel>
            <PanelHeader
              title="Order ticket"
              subtitle={`${side === "buy" ? "Buy" : "Sell"} ${symbol}`}
              action={
                <div className="text-right">
                  <p className="num text-sm text-paper">{ticker.data ? money(ticker.data.price) : "—"}</p>
                  <p className="text-2xs text-paper-faint">
                    {ticker.data?.is_demo ? "demo quote" : ticker.data?.source ?? "quote"}
                  </p>
                </div>
              }
            />
            <PanelBody>
              <form onSubmit={submitOrder} className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setSide("buy")}
                    className={`flex h-9 items-center justify-center gap-1.5 rounded-lg border text-xs transition ${
                      side === "buy"
                        ? "border-gain/50 bg-gain/10 text-gain"
                        : "border-line-strong text-paper-muted hover:bg-ink-800"
                    }`}
                  >
                    <ArrowUpRight className="h-3.5 w-3.5" /> Buy
                  </button>
                  <button
                    type="button"
                    onClick={() => setSide("sell")}
                    className={`flex h-9 items-center justify-center gap-1.5 rounded-lg border text-xs transition ${
                      side === "sell"
                        ? "border-loss/50 bg-loss/10 text-loss"
                        : "border-line-strong text-paper-muted hover:bg-ink-800"
                    }`}
                  >
                    <ArrowDownRight className="h-3.5 w-3.5" /> Sell
                  </button>
                </div>

                <Field label="Instrument" htmlFor="symbol">
                  <Select id="symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)}>
                    {(instruments.data?.instruments ?? [{ symbol: "BTC/USDT" }]).map((instrument) => (
                      <option key={instrument.symbol} value={instrument.symbol}>
                        {instrument.symbol}
                      </option>
                    ))}
                  </Select>
                </Field>

                <div className="grid grid-cols-2 gap-2">
                  <Field label="Type" htmlFor="order_type">
                    <Select
                      id="order_type"
                      value={orderType}
                      onChange={(event) => setOrderType(event.target.value as typeof orderType)}
                    >
                      <option value="market">Market</option>
                      <option value="limit">Limit</option>
                      <option value="stop">Stop</option>
                      <option value="stop_limit">Stop limit</option>
                    </Select>
                  </Field>
                  <Field label="Quantity" htmlFor="quantity">
                    <Input
                      id="quantity"
                      type="number"
                      step="any"
                      min="0"
                      value={quantity}
                      onChange={(event) => setQuantity(event.target.value)}
                      required
                    />
                  </Field>
                </div>

                {orderType !== "market" ? (
                  <Field label={orderType.startsWith("stop") ? "Stop price" : "Limit price"} htmlFor="price">
                    <Input
                      id="price"
                      type="number"
                      step="any"
                      min="0"
                      value={price}
                      onChange={(event) => setPrice(event.target.value)}
                      required
                    />
                  </Field>
                ) : null}

                <div className="grid grid-cols-2 gap-2">
                  <Field label="Stop loss" htmlFor="stop_loss" hint="Required for live entries">
                    <Input
                      id="stop_loss"
                      type="number"
                      step="any"
                      min="0"
                      value={stopLoss}
                      onChange={(event) => setStopLoss(event.target.value)}
                    />
                  </Field>
                  <Field label="Take profit" htmlFor="take_profit">
                    <Input
                      id="take_profit"
                      type="number"
                      step="any"
                      min="0"
                      value={takeProfit}
                      onChange={(event) => setTakeProfit(event.target.value)}
                    />
                  </Field>
                </div>

                <Field label="Mode" htmlFor="mode">
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setMode("paper")}
                      className={`h-9 rounded-lg border text-xs transition ${
                        mode === "paper" ? "border-info/50 bg-info/10 text-info" : "border-line-strong text-paper-muted"
                      }`}
                    >
                      Paper (simulated)
                    </button>
                    <button
                      type="button"
                      onClick={() => liveEnabled && setMode("live")}
                      disabled={!liveEnabled}
                      title={liveEnabled ? undefined : "Live execution needs eligibility, authorisation and an open platform gate"}
                      className={`h-9 rounded-lg border text-xs transition disabled:cursor-not-allowed disabled:opacity-40 ${
                        mode === "live" ? "border-warn/50 bg-warn/10 text-warn" : "border-line-strong text-paper-muted"
                      }`}
                    >
                      Live
                    </button>
                  </div>
                </Field>

                {mode === "paper" ? (
                  <Field
                    label="Paper session"
                    htmlFor="session"
                    hint={sessionList.length ? undefined : "Start a session on the Strategies page to attribute fills."}
                  >
                    <Select id="session" value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
                      <option value="">No session (unattributed)</option>
                      {sessionList.map((session) => (
                        <option key={session.id} value={session.id}>
                          {session.instrument_symbol} · {titleCase(session.status)} · {session.id.slice(0, 8)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ) : null}

                <Field label="Reason" htmlFor="reason" hint="Stored on the trade record.">
                  <Textarea
                    id="reason"
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    className="min-h-16"
                  />
                </Field>

                <div className="flex items-center justify-between rounded-lg border border-line-soft bg-ink-900 px-3 py-2 text-xs">
                  <span className="text-paper-faint">Estimated notional</span>
                  <span className="num text-paper">{money(notional)}</span>
                </div>

                {lastError ? (
                  <p className="rounded-lg border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">{lastError}</p>
                ) : null}

                <Button type="submit" fullWidth loading={busy} variant={side === "buy" ? "primary" : "danger"}>
                  {mode === "paper" ? "Submit simulated order" : "Submit live order"}
                </Button>
                <p className="text-center text-2xs text-paper-faint">
                  Idempotency key <span className="num">{idempotencyKey.slice(0, 8)}</span> · blocks duplicate submission
                </p>
              </form>
            </PanelBody>
          </Panel>

          {lastDecision ? (
            <Panel className={lastDecision.decision === "approved" ? "border-gain/30" : "border-loss/40"}>
              <PanelHeader
                title="Risk evaluation"
                subtitle="Independent of the strategy layer"
                action={
                  <Badge tone={lastDecision.decision === "approved" ? "gain" : "loss"}>{lastDecision.decision}</Badge>
                }
              />
              <ul className="divide-y divide-line-soft/70">
                {lastDecision.checks.map((check) => (
                  <li key={check.code} className="flex items-start justify-between gap-3 px-5 py-2.5">
                    <div>
                      <p className="num text-2xs text-paper">{check.code}</p>
                      <p className="mt-0.5 text-2xs text-paper-faint">{check.message}</p>
                    </div>
                    <span className={check.passed ? "text-gain" : "text-loss"}>
                      {check.passed ? "pass" : "block"}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}

          <Panel>
            <PanelHeader title="Guards" subtitle="Always on, whatever the strategy wants" />
            <PanelBody className="space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-2 text-paper-muted">
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden /> Kill switch
                </span>
                <Badge tone={killEngaged ? "loss" : "gain"}>{killEngaged ? "engaged" : "clear"}</Badge>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-paper-muted">Platform live gate</span>
                <Badge tone={platform?.live_trading_enabled ? "warn" : "neutral"}>
                  {platform?.live_trading_enabled ? "open" : "closed"}
                </Badge>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-paper-muted">Demo executions today</span>
                <span className="num text-paper">{state.data?.demo_executions_today ?? 0}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-paper-muted">Your live authorisation</span>
                <StatusBadge status={state.data?.live.status ?? "not_started"} />
              </div>
            </PanelBody>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel>
            <div className="flex items-center justify-between gap-2 px-4 pt-3">
              <Tabs
                tabs={[
                  { id: "positions", label: "Positions", count: openPositions.length },
                  { id: "orders", label: "Orders", count: orders.data?.orders.length },
                  { id: "trades", label: "Trades", count: trades.data?.trades.length },
                ]}
                active={tab}
                onChange={setTab}
                className="border-0"
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  state.refetch();
                  orders.refetch();
                  trades.refetch();
                }}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh
              </Button>
            </div>

            {tab === "positions" ? (
              state.loading ? (
                <div className="p-5">
                  <Skeleton className="h-24 w-full" />
                </div>
              ) : openPositions.length ? (
                <Table>
                  <THead>
                    <TR>
                      <TH>Instrument</TH>
                      <TH>Side</TH>
                      <TH align="right">Qty</TH>
                      <TH align="right">Entry</TH>
                      <TH align="right">Mark</TH>
                      <TH align="right">Unrealised</TH>
                      <TH>Mode</TH>
                      <TH />
                    </TR>
                  </THead>
                  <TBody>
                    {openPositions.map((position) => (
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
                          <div className="flex items-center gap-1.5">
                            <StatusBadge status={position.mode} />
                            {position.mode === "paper" ? <DemoBadge /> : null}
                          </div>
                        </TD>
                        <TD align="right">
                          <Button size="sm" variant="secondary" onClick={() => closePosition(position)} disabled={busy}>
                            Close
                          </Button>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              ) : (
                <EmptyState title="No open positions" description="Orders that fill create a position here." />
              )
            ) : null}

            {tab === "orders" ? (
              orders.loading ? (
                <div className="p-5">
                  <Skeleton className="h-24 w-full" />
                </div>
              ) : orders.data && orders.data.orders.length ? (
                <Table>
                  <THead>
                    <TR>
                      <TH>Instrument</TH>
                      <TH>Side</TH>
                      <TH>Type</TH>
                      <TH align="right">Qty</TH>
                      <TH align="right">Filled</TH>
                      <TH>Status</TH>
                      <TH>Created</TH>
                      <TH />
                    </TR>
                  </THead>
                  <TBody>
                    {orders.data.orders.map((order) => (
                      <TR key={order.id}>
                        <TD mono>{order.symbol}</TD>
                        <TD>{order.side}</TD>
                        <TD>{titleCase(order.order_type)}</TD>
                        <TD align="right" mono>
                          {order.quantity}
                        </TD>
                        <TD align="right" mono>
                          {order.filled_qty ?? 0}
                        </TD>
                        <TD>
                          <div className="flex flex-col gap-1">
                            <StatusBadge status={order.status} />
                            {order.rejection_reason ? (
                              <span
                                className="max-w-[16rem] truncate text-2xs text-loss"
                                title={order.rejection_reason}
                              >
                                {order.rejection_reason}
                              </span>
                            ) : null}
                          </div>
                        </TD>
                        <TD>{dateTime(order.created_at)}</TD>
                        <TD align="right">
                          {["open", "pending", "partially_filled"].includes(order.status) ? (
                            <Button size="sm" variant="ghost" onClick={() => cancelOrder(order)} disabled={busy}>
                              <X className="h-3 w-3" />
                            </Button>
                          ) : null}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              ) : (
                <EmptyState title="No orders yet" description="Submitted orders appear here with their risk decision." />
              )
            ) : null}

            {tab === "trades" ? (
              trades.loading ? (
                <div className="p-5">
                  <Skeleton className="h-24 w-full" />
                </div>
              ) : trades.data && trades.data.trades.length ? (
                <Table>
                  <THead>
                    <TR>
                      <TH>Instrument</TH>
                      <TH>Side</TH>
                      <TH align="right">Net P&amp;L</TH>
                      <TH align="right">Fees</TH>
                      <TH align="right">Slippage</TH>
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
                        <TD align="right" mono>
                          {bps(trade.slippage_actual_bps)}
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
                <EmptyState title="No closed trades" description="Close a position to produce an immutable trade record." />
              )
            ) : null}
          </Panel>

          {state.error ? <ErrorNote message={state.error} onRetry={state.refetch} /> : null}

          <div className="rounded-xl border border-line-soft bg-ink-900/50 px-5 py-4">
            <p className="text-xs leading-relaxed text-paper-faint">
              Orders are validated before execution, not after. A rejected order keeps every check — including
              the ones that passed — so the reason is never a mystery.
            </p>
          </div>
        </div>
      </div>

      <TradeDetailDialog tradeId={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
}
