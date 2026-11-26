"use client";

import * as React from "react";
import { Activity, CircleSlash, Plug, ShieldAlert, Sparkles } from "lucide-react";
import { errorMessage } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { cn } from "@/lib/cn";
import { money, number, price, relativeTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import type { Connection, RiskDecision } from "@/lib/types";
import {
  MARKET_LABELS,
  closeContract,
  decideSignal,
  fetchAutomation,
  fetchSignals,
  fetchStatus,
  fetchSymbols,
  fetchTicker,
  openContract,
  openSession,
  previewContract,
  saveAutomation,
  type DerivAutomation,
  type DerivPreview,
  type DerivSignal,
} from "@/lib/deriv";

const DURATIONS = [
  { value: 1, unit: "t", label: "1 tick" },
  { value: 5, unit: "t", label: "5 ticks" },
  { value: 15, unit: "m", label: "15 min" },
  { value: 1, unit: "h", label: "1 hour" },
  { value: 1, unit: "d", label: "1 day" },
];

type Props = { connections: Connection[] };

export function DerivTerminal({ connections }: Props) {
  const toast = useToast();
  const [connectionId, setConnectionId] = React.useState("");
  const [symbol, setSymbol] = React.useState("R_100");
  const [side, setSide] = React.useState<"buy" | "sell">("buy");
  const [stake, setStake] = React.useState("10");
  const [durationIndex, setDurationIndex] = React.useState(1);
  const [busy, setBusy] = React.useState(false);
  const [preview, setPreview] = React.useState<DerivPreview | null>(null);
  const [risk, setRisk] = React.useState<RiskDecision | null>(null);
  const [liveArmed, setLiveArmed] = React.useState(false);

  const deriv = connections.filter((item) => item.provider === "deriv" && item.status !== "revoked");
  const activeConnectionId = connectionId || deriv[0]?.id || "";

  const symbols = useApi((signal) => fetchSymbols(false, signal));
  const status = useApi(
    (signal) => (activeConnectionId ? fetchStatus(activeConnectionId, signal) : Promise.resolve(null)),
    [activeConnectionId],
  );
  const ticker = useApi((signal) => fetchTicker(symbol, signal), [symbol]);
  const automation = useApi(
    (signal) =>
      activeConnectionId ? fetchAutomation(activeConnectionId, signal) : Promise.resolve({ automation: null }),
    [activeConnectionId],
  );
  const signals = useApi(
    (signal) =>
      activeConnectionId ? fetchSignals(activeConnectionId, "pending", signal) : Promise.resolve({ signals: [] }),
    [activeConnectionId],
  );
  const recent = useApi(
    (signal) =>
      activeConnectionId ? fetchSignals(activeConnectionId, "", signal) : Promise.resolve({ signals: [] }),
    [activeConnectionId],
  );

  useInterval(() => ticker.refetch(), 5000);

  const duration = DURATIONS[durationIndex] ?? { value: 5, unit: "t", label: "5 ticks" };
  const isDemo = Boolean(status.data?.connection.is_demo);
  const scope = status.data?.gate.scope ?? "blocked";

  const markets = React.useMemo(() => {
    const rows = symbols.data?.markets ?? {};
    return Object.entries(rows).map(([market, items]) => ({
      market,
      label: MARKET_LABELS[market] ?? market,
      items,
    }));
  }, [symbols.data]);

  const activeSymbol = React.useMemo(() => {
    for (const group of markets) {
      const found = group.items.find((item) => item.symbol === symbol);
      if (found) return found;
    }
    return null;
  }, [markets, symbol]);

  const venueOpen = Boolean(activeSymbol?.exchange_is_open) && !activeSymbol?.suspended;

  function request() {
    return {
      symbol,
      side,
      stake: Number(stake) || 0,
      duration: duration.value,
      duration_unit: duration.unit,
    };
  }

  async function runPreview() {
    if (!activeConnectionId) return;
    setBusy(true);
    try {
      setPreview(await previewContract(activeConnectionId, request()));
    } catch (error) {
      setPreview(null);
      toast.error("Quote unavailable", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!activeConnectionId) return;
    if (!isDemo && !liveArmed) {
      toast.error("Live contract not sent", "Tick the confirmation first: this order uses real funds.");
      return;
    }
    setBusy(true);
    try {
      const result = await openContract(activeConnectionId, request());
      setRisk(result.risk);
      if (result.approved) {
        toast.success(
          isDemo ? "Demo contract opened" : "Live contract opened",
          `${symbol} · stake ${money(Number(stake))} · contract ${result.venue?.contract_id ?? result.order.provider_order_id ?? "—"}`,
        );
      } else {
        toast.error(
          "Risk engine rejected the contract",
          result.risk?.checks?.find((check) => !check.passed)?.message ?? result.message ?? "Nothing was sent to Deriv.",
        );
      }
      status.refetch();
    } catch (error) {
      toast.error("Contract not submitted", errorMessage(error));
    } finally {
      setBusy(false);
      setLiveArmed(false);
    }
  }

  async function session(action: "connect" | "reconnect" | "close") {
    if (!activeConnectionId) return;
    setBusy(true);
    try {
      await openSession(activeConnectionId, action);
      toast.success(action === "close" ? "Trading session closed" : "Trading session ready");
      status.refetch();
    } catch (error) {
      toast.error("Session action failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function flatten(contractId: string) {
    if (!activeConnectionId) return;
    setBusy(true);
    try {
      await closeContract(activeConnectionId, contractId);
      toast.info("Close request sent to Deriv");
      status.refetch();
    } catch (error) {
      toast.error("Close failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  if (!deriv.length) {
    return (
      <div className="space-y-3 p-4">
        <div className="rounded-xl border border-line-soft bg-obsidian-900/60 p-4">
          <p className="flex items-center gap-2 text-sm text-paper">
            <Plug className="h-4 w-4 text-champagne-300" aria-hidden />
            No Deriv account connected
          </p>
          <p className="mt-1.5 text-2xs leading-relaxed text-paper-muted">
            Connect a Deriv account with a trading-scoped Personal Access Token. A demo account needs no
            live authorisation; a real account needs the full authorisation checklist before any order
            leaves the platform.
          </p>
          <a
            href="/app/accounts"
            className="mt-3 inline-flex text-2xs text-champagne-300 underline-offset-4 hover:underline"
          >
            Connect an account
          </a>
        </div>
      </div>
    );
  }

  const quote = ticker.data;

  return (
    <div className="space-y-4 p-4">
      <div className="rounded-xl border border-line-soft bg-obsidian-900/60 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-xs text-paper">
              <Activity className="h-3.5 w-3.5 text-champagne-300" aria-hidden />
              {status.data?.connection.label ?? "Deriv"}
              {isDemo ? <Badge tone="info">demo</Badge> : <Badge tone="warn">real funds</Badge>}
            </p>
            <p className="mt-1 text-3xs text-paper-faint">
              {status.data?.connection.account_id ?? "account pending"} ·{" "}
              {status.data?.session.state ? status.data.session.state.replace(/_/g, " ") : "no session"} · scope{" "}
              {scope}
            </p>
          </div>
          {status.data?.session.connected ? (
            <Button size="sm" variant="ghost" onClick={() => session("close")} disabled={busy}>
              <CircleSlash className="h-3 w-3" />
              Close session
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => session("connect")}
              disabled={busy || !status.data?.gate.allowed}
            >
              <Plug className="h-3 w-3" />
              Open session
            </Button>
          )}
        </div>
        {deriv.length > 1 ? (
          <Select
            aria-label="Deriv account"
            className="mt-2 h-8 text-2xs"
            value={activeConnectionId}
            onChange={(event) => setConnectionId(event.target.value)}
          >
            {deriv.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </Select>
        ) : null}
        {status.data && !status.data.gate.allowed ? (
          <p className="mt-2 flex items-start gap-1.5 text-3xs leading-relaxed text-warn/90">
            <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            {status.data.gate.blocking_message}
          </p>
        ) : null}
        {status.data?.contracts_error ? (
          <p className="mt-2 text-3xs text-loss/90">{status.data.contracts_error}</p>
        ) : null}
      </div>

      <div className="grid gap-3">
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="label mb-1 block">Market</span>
            <Select
              aria-label="Market"
              value={symbol}
              onChange={(event) => {
                setSymbol(event.target.value);
                setPreview(null);
              }}
              className="h-9 text-xs"
            >
              {markets.length ? (
                markets.map((group) => (
                  <optgroup key={group.market} label={group.label}>
                    {group.items.map((item) => (
                      <option key={item.symbol} value={item.symbol}>
                        {item.symbol} — {item.name}
                      </option>
                    ))}
                  </optgroup>
                ))
              ) : (
                <option value={symbol}>{symbol}</option>
              )}
            </Select>
          </label>
          <label className="block">
            <span className="label mb-1 block">Expiry</span>
            <Select
              aria-label="Contract expiry"
              value={durationIndex}
              onChange={(event) => setDurationIndex(Number(event.target.value))}
              className="h-9 text-xs"
            >
              {DURATIONS.map((item, index) => (
                <option key={item.label} value={index}>
                  {item.label}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <div className="flex items-baseline justify-between rounded-lg border border-line-soft bg-obsidian-900/60 px-3 py-2">
          <div>
            <p className="text-3xs uppercase tracking-label text-paper-faint">{symbol}</p>
            <p className="num text-lg text-paper">
              {quote ? price(quote.price) : ticker.loading ? "—" : "no quote"}
            </p>
          </div>
          <p className="text-3xs text-paper-faint">
            {quote ? `${Math.round(quote.age_seconds)}s ago` : "public gateway"}
            {venueOpen ? "" : " · venue reports closed"}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setSide("buy")}
            aria-pressed={side === "buy"}
            className={cn(
              "rounded-lg border py-2 text-xs transition",
              side === "buy"
                ? "border-gain/40 bg-gain/10 text-gain"
                : "border-line-strong text-paper-muted hover:text-paper",
            )}
          >
            Rise · CALL
          </button>
          <button
            type="button"
            onClick={() => setSide("sell")}
            aria-pressed={side === "sell"}
            className={cn(
              "rounded-lg border py-2 text-xs transition",
              side === "sell"
                ? "border-loss/40 bg-loss/10 text-loss"
                : "border-line-strong text-paper-muted hover:text-paper",
            )}
          >
            Fall · PUT
          </button>
        </div>

        <label className="block">
          <span className="label mb-1 block">Stake ({status.data?.connection.currency ?? "USD"})</span>
          <Input
            type="number"
            min={1}
            step={1}
            inputMode="decimal"
            value={stake}
            onChange={(event) => setStake(event.target.value)}
            className="num h-9 text-center text-sm"
            aria-label="Stake"
          />
        </label>

        {preview ? (
          <div className="rounded-lg border border-line-soft bg-obsidian-900/60 px-3 py-2 text-2xs">
            <div className="flex items-center justify-between">
              <span className="text-paper-faint">Payout if correct</span>
              <span className="num text-paper">{money(preview.proposal.payout)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-paper-faint">Payout / stake</span>
              <span className="num text-paper-muted">
                {number(preview.terms.payout_pct, 2)}% margin
              </span>
            </div>
            {preview.proposal.longcode ? (
              <p className="mt-1.5 text-3xs leading-relaxed text-paper-faint">{preview.proposal.longcode}</p>
            ) : null}
          </div>
        ) : null}

        <div className="grid grid-cols-2 gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={runPreview}
            loading={busy}
            disabled={!activeConnectionId}
          >
            Quote
          </Button>
          <Button
            size="sm"
            variant={isDemo ? "primary" : "danger"}
            onClick={submit}
            loading={busy}
            disabled={!activeConnectionId || !venueOpen}
          >
            {isDemo ? "Place demo" : "Place live"}
          </Button>
        </div>

        {!isDemo ? (
          <label className="flex items-start gap-2 rounded-lg border border-loss/25 bg-loss/5 px-2.5 py-2 text-3xs leading-relaxed text-paper-muted">
            <input
              type="checkbox"
              checked={liveArmed}
              onChange={(event) => setLiveArmed(event.target.checked)}
              className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-champagne-500"
            />
            I understand this submits a real-money contract on my Deriv account, and that the risk engine
            may still reject it.
          </label>
        ) : null}

        {risk ? <RiskTrace risk={risk} /> : null}
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <p className="label">Open contracts</p>
          <button
            type="button"
            onClick={() => status.refetch()}
            className="text-3xs text-paper-faint underline-offset-4 hover:text-paper-muted hover:underline"
          >
            Refresh
          </button>
        </div>
        {status.data?.open_contracts?.length ? (
          <ul className="space-y-1.5">
            {status.data.open_contracts.map((contract) => (
              <li
                key={contract.contract_id}
                className="flex items-center justify-between rounded-lg border border-line-soft bg-obsidian-900/50 px-2.5 py-2"
              >
                <div className="min-w-0">
                  <p className="text-2xs text-paper">
                    {contract.symbol ?? symbol} · {contract.contract_type ?? "contract"}
                  </p>
                  <p className="num text-3xs text-paper-faint">
                    stake {money(contract.buy_price ?? null)} · P/L {money(contract.profit ?? null)}
                  </p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => flatten(contract.contract_id)} disabled={busy}>
                  Close
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-3xs text-paper-faint">No open contracts on this account.</p>
        )}
      </div>

      <AutomationCard
        connectionId={activeConnectionId}
        config={automation.data?.automation ?? null}
        gateAllowed={Boolean(status.data?.gate.allowed)}
        symbols={markets.flatMap((group) =>
          group.items.map((item) => ({ symbol: item.symbol, name: item.name })),
        )}
        onSaved={() => {
          automation.refetch();
          signals.refetch();
          recent.refetch();
        }}
      />

      {signals.data?.signals.length ? (
        <div className="space-y-1.5">
          <p className="label">Pending AI signals</p>
          {signals.data.signals.map((signal) => (
            <SignalRow
              key={signal.id}
              signal={signal}
              busy={busy}
              onDecide={async (decision) => {
                setBusy(true);
                try {
                  const result = await decideSignal(signal.id, decision);
                  if (decision === "reject") {
                    toast.success("Signal rejected");
                  } else if (result.approved === false) {
                    const reasons = (result.risk?.failed_rules ?? [])
                      .map((rule) => rule.message)
                      .filter(Boolean);
                    toast.error("Risk engine refused the signal", reasons.join("; ") || "No reason recorded.");
                  } else {
                    toast.success("Signal executed", "The venue confirmed the contract.");
                  }
                  signals.refetch();
                  recent.refetch();
                  status.refetch();
                } catch (error) {
                  toast.error("Signal action failed", errorMessage(error));
                } finally {
                  setBusy(false);
                }
              }}
            />
          ))}
        </div>
      ) : null}

      <RecentSignals signals={recent.data?.signals ?? []} />
    </div>
  );
}

const SIGNAL_TONES: Record<string, string> = {
  executed: "border-gain/25 bg-gain/5 text-gain",
  pending: "border-line-soft bg-obsidian-900/60 text-paper",
  rejected: "border-loss/25 bg-loss/5 text-loss",
  expired: "border-line-soft bg-obsidian-900/40 text-paper-faint",
  failed: "border-loss/25 bg-loss/5 text-loss",
};

function RecentSignals({ signals }: { signals: DerivSignal[] }) {
  if (!signals.length) return null;
  return (
    <div className="space-y-1.5">
      <p className="label">Recent signals</p>
      {signals.slice(0, 8).map((signal) => (
        <div
          key={signal.id}
          className="rounded-lg border border-line-soft bg-obsidian-900/40 px-2.5 py-2"
        >
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-2xs text-paper">
              {signal.symbol} · {signal.contract_type} · {money(signal.stake)}
            </p>
            <span
              className={cn(
                "shrink-0 rounded-full border px-1.5 py-0.5 text-3xs capitalize",
                SIGNAL_TONES[signal.status] ?? "border-line-soft bg-obsidian-900/60 text-paper-faint",
              )}
            >
              {signal.status}
            </span>
          </div>
          <p className="mt-1 text-3xs leading-relaxed text-paper-faint">
            {signal.decided_at ? relativeTime(signal.decided_at) : relativeTime(signal.created_at)}
            {signal.order_id ? ` · order ${signal.order_id.slice(0, 8)}` : ""}
          </p>
          {signal.error ? (
            <p className="mt-1 text-3xs leading-relaxed text-loss">{signal.error}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function RiskTrace({ risk }: { risk: RiskDecision }) {
  const failed = (risk.checks ?? []).filter((check) => !check.passed);
  return (
    <div
      className={cn(
        "rounded-lg border px-2.5 py-2 text-3xs",
        risk.decision === "approved" ? "border-gain/25 bg-gain/5" : "border-loss/25 bg-loss/5",
      )}
    >
      <p className={risk.decision === "approved" ? "text-gain" : "text-loss"}>
        Risk engine: {risk.decision}
        {failed.length ? ` · ${failed.length} blocking check${failed.length > 1 ? "s" : ""}` : ""}
      </p>
      <ul className="mt-1 space-y-0.5">
        {(failed.length ? failed : (risk.checks ?? []).slice(0, 3)).map((check) => (
          <li key={check.code} className="text-paper-faint">
            {check.passed ? "✓" : "✕"} {check.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SignalRow({
  signal,
  busy,
  onDecide,
}: {
  signal: DerivSignal;
  busy: boolean;
  onDecide: (decision: "approve" | "reject") => void;
}) {
  return (
    <div className="rounded-lg border border-line-soft bg-obsidian-900/50 px-2.5 py-2">
      <div className="flex items-center justify-between">
        <p className="text-2xs text-paper">
          {signal.symbol} · {signal.contract_type} · {money(signal.stake)}
        </p>
        <p className="text-3xs text-paper-faint">{relativeTime(signal.created_at)}</p>
      </div>
      <p className="mt-1 text-3xs leading-relaxed text-paper-faint">{signal.reason}</p>
      <div className="mt-1.5 flex gap-1.5">
        <Button size="sm" variant="secondary" onClick={() => onDecide("approve")} disabled={busy}>
          Approve
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onDecide("reject")} disabled={busy}>
          Reject
        </Button>
      </div>
    </div>
  );
}

function AutomationCard({
  connectionId,
  config,
  gateAllowed,
  symbols,
  onSaved,
}: {
  connectionId: string;
  config: DerivAutomation | null;
  gateAllowed: boolean;
  symbols: { symbol: string; name: string }[];
  onSaved: () => void;
}) {
  const toast = useToast();
  const [enabled, setEnabled] = React.useState(config?.enabled ?? false);
  const [mode, setMode] = React.useState<"approval" | "autonomous">(config?.mode ?? "approval");
  const [symbol, setSymbol] = React.useState(config?.symbol ?? "R_100");
  const [stake, setStake] = React.useState(String(config?.stake ?? 10));
  const [maxStake, setMaxStake] = React.useState(String(config?.max_stake_per_trade ?? 25));
  const [dailyLoss, setDailyLoss] = React.useState(String(config?.daily_loss_limit ?? 100));
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!config) return;
    setEnabled(config.enabled);
    setMode(config.mode);
    setSymbol(config.symbol);
    setStake(String(config.stake));
    setMaxStake(String(config.max_stake_per_trade));
    setDailyLoss(String(config.daily_loss_limit));
  }, [config]);

  async function save() {
    setBusy(true);
    try {
      await saveAutomation(connectionId, {
        enabled,
        mode,
        symbol,
        stake: Number(stake) || 10,
        max_stake_per_trade: Number(maxStake) || 25,
        daily_loss_limit: Number(dailyLoss) || 100,
      });
      toast.success("Automation saved", enabled ? `${mode} mode · ${symbol}` : "Automation paused");
      onSaved();
    } catch (error) {
      toast.error("Automation not saved", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-line-soft bg-obsidian-900/60 p-3">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs text-paper">
          <Sparkles className="h-3.5 w-3.5 text-champagne-300" aria-hidden />
          Autotrade
        </p>
        <Badge tone={enabled ? "gain" : "neutral"}>{enabled ? "running" : "paused"}</Badge>
      </div>
      <p className="mt-1 text-3xs leading-relaxed text-paper-faint">
        The baseline trigger is an EMA cross with an RSI filter on 5-minute candles. It proposes; the
        deterministic risk engine still decides. Approval mode waits for you.
      </p>

      <div className="mt-2 grid grid-cols-2 gap-2">
        <label className="block">
          <span className="label mb-1 block">Mode</span>
          <Select
            aria-label="Automation mode"
            value={mode}
            onChange={(event) => setMode(event.target.value as "approval" | "autonomous")}
            className="h-8 text-2xs"
          >
            <option value="approval">Approval</option>
            <option value="autonomous">Autonomous</option>
          </Select>
        </label>
        <label className="block">
          <span className="label mb-1 block">Symbol</span>
          <Select
            aria-label="Automation symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            className="h-8 text-2xs"
          >
            {symbols.length ? (
              symbols.map((row) => (
                <option key={row.symbol} value={row.symbol}>
                  {row.name}
                </option>
              ))
            ) : (
              <option value={symbol}>{symbol}</option>
            )}
          </Select>
        </label>
        <label className="block">
          <span className="label mb-1 block">Stake</span>
          <Input
            type="number"
            value={stake}
            onChange={(event) => setStake(event.target.value)}
            className="num h-8 text-2xs"
            aria-label="Automation stake"
          />
        </label>
        <label className="block">
          <span className="label mb-1 block">Max stake / trade</span>
          <Input
            type="number"
            value={maxStake}
            onChange={(event) => setMaxStake(event.target.value)}
            className="num h-8 text-2xs"
            aria-label="Maximum stake per trade"
          />
        </label>
        <label className="col-span-2 block">
          <span className="label mb-1 block">Daily loss limit</span>
          <Input
            type="number"
            value={dailyLoss}
            onChange={(event) => setDailyLoss(event.target.value)}
            className="num h-8 text-2xs"
            aria-label="Daily loss limit"
          />
        </label>
      </div>

      {mode === "autonomous" && !gateAllowed ? (
        <p className="mt-2 text-3xs text-warn/90">
          Autonomous mode stays blocked until the connection passes every execution gate.
        </p>
      ) : null}

      <div className="mt-2 flex items-center justify-between">
        <label className="flex items-center gap-2 text-3xs text-paper-muted">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            className="h-3.5 w-3.5 accent-champagne-500"
          />
          Enabled
        </label>
        <Button size="sm" variant="secondary" onClick={save} loading={busy} disabled={!connectionId}>
          Save
        </Button>
      </div>
      {config?.halt_reason ? <p className="mt-1.5 text-3xs text-loss/90">{config.halt_reason}</p> : null}
    </div>
  );
}
