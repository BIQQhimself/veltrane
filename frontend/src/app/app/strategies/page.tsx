"use client";

import * as React from "react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime, money, percent, signedMoney } from "@/lib/format";
import { Badge, DemoBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, KeyValue, Skeleton } from "@/components/ui/data";
import { Dialog, Tabs } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import type { Backtest, PaperSession, Strategy } from "@/lib/types";

type StrategyList = { strategies: Strategy[]; disclaimer: string };
type BacktestList = { backtests: Backtest[] };
type SessionList = { sessions: PaperSession[] };

const TIMEFRAMES = ["15m", "1h", "4h", "1d"] as const;

export default function StrategiesPage() {
  const toast = useToast();
  const { hasFeature, entitlements } = useAuth();
  const strategies = useApi<StrategyList>((signal) => api("/strategies", { signal }));
  const backtests = useApi<BacktestList>((signal) => api("/backtests", { signal, query: { limit: 20 } }));
  const sessions = useApi<SessionList>((signal) => api("/paper-sessions", { signal }));

  const [tab, setTab] = React.useState("library");
  const [selected, setSelected] = React.useState<Strategy | null>(null);
  const [detail, setDetail] = React.useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [backtestCode, setBacktestCode] = React.useState("");
  const [symbol, setSymbol] = React.useState("BTC/USDT");
  const [timeframe, setTimeframe] = React.useState<(typeof TIMEFRAMES)[number]>("1h");
  const [walkForward, setWalkForward] = React.useState(false);

  const canBacktest = hasFeature("backtesting");
  const library = React.useMemo(() => strategies.data?.strategies ?? [], [strategies.data]);
  const libraryCodes = (entitlements?.limits?.strategy_library as string[] | undefined) ?? null;

  React.useEffect(() => {
    if (!backtestCode && library.length) setBacktestCode(library[0]!.code);
  }, [library, backtestCode]);

  async function openStrategy(strategy: Strategy) {
    setSelected(strategy);
    setDetail(null);
    try {
      const body = await api<{ strategy: Record<string, unknown> }>(`/strategies/${strategy.code}`);
      setDetail(body.strategy);
    } catch (error) {
      toast.error("Could not load strategy", errorMessage(error));
    }
  }

  async function runBacktest() {
    setBusy(true);
    try {
      const result = await api<Backtest>("/backtests", {
        method: "POST",
        body: { strategy_code: backtestCode, symbol, timeframe, walk_forward: walkForward },
      });
      toast.success(
        "Backtest complete",
        `${result.trades_count} trades · net ${money(Number(result.metrics.net_pnl ?? 0))}`,
      );
      backtests.refetch();
      setTab("backtests");
    } catch (error) {
      toast.error("Backtest failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function startSession(code: string) {
    setBusy(true);
    try {
      await api("/paper-sessions", {
        method: "POST",
        body: { strategy_code: code, symbol, timeframe },
      });
      toast.success("Paper session started", "Open the terminal to place simulated orders against it.");
      sessions.refetch();
      setTab("sessions");
    } catch (error) {
      toast.error("Could not start session", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function tick(session: PaperSession) {
    setBusy(true);
    try {
      const result = await api<{ actions?: string[] }>(`/paper-sessions/${session.id}/tick`, { method: "POST" });
      toast.info("Session ticked", result.actions?.length ? result.actions.join(" · ") : "No signals this tick.");
      sessions.refetch();
    } catch (error) {
      toast.error("Tick failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function stop(session: PaperSession) {
    setBusy(true);
    try {
      await api(`/paper-sessions/${session.id}/stop`, { method: "POST" });
      toast.info("Session stopped");
      sessions.refetch();
    } catch (error) {
      toast.error("Could not stop session", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Research"
        title="Strategies"
        description="Versioned rules with stated limitations. Backtests are net of modelled fees, spread, slippage and funding — and they are not predictions."
        action={
          <Badge tone="gold">
            {libraryCodes ? `${libraryCodes.length} in your library` : "core library"}
          </Badge>
        }
      />

      <Tabs
        tabs={[
          { id: "library", label: "Library", count: library.length },
          { id: "backtests", label: "Backtests", count: backtests.data?.backtests.length },
          { id: "sessions", label: "Paper sessions", count: sessions.data?.sessions.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "library" ? (
        strategies.loading ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        ) : library.length ? (
          <>
            <div className="grid gap-4 md:grid-cols-2">
              {library.map((strategy) => (
                <Panel key={strategy.code} className="flex flex-col">
                  <PanelHeader
                    title={strategy.name}
                    subtitle={strategy.category}
                    action={strategy.version ? <Badge tone="neutral">v{strategy.version}</Badge> : null}
                  />
                  <PanelBody className="flex flex-1 flex-col">
                    <p className="text-xs leading-relaxed text-paper-muted">{strategy.summary}</p>
                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {(strategy.supported_markets ?? []).map((market) => (
                        <Badge key={market} tone="outline">
                          {market}
                        </Badge>
                      ))}
                      {(strategy.timeframes ?? []).map((tf) => (
                        <Badge key={tf} tone="outline">
                          {tf}
                        </Badge>
                      ))}
                    </div>
                    <div className="mt-auto flex items-center justify-between pt-5">
                      <button
                        type="button"
                        onClick={() => openStrategy(strategy)}
                        className="text-xs text-champagne-300 hover:text-champagne-200"
                      >
                        View specification
                      </button>
                      <Button size="sm" variant="secondary" disabled={busy} onClick={() => startSession(strategy.code)}>
                        Paper session
                      </Button>
                    </div>
                  </PanelBody>
                </Panel>
              ))}
            </div>
            <p className="text-2xs leading-relaxed text-paper-faint">{strategies.data?.disclaimer}</p>
          </>
        ) : (
          <EmptyState title="No strategies available" description="System strategies are seeded by the operator." />
        )
      ) : null}

      {tab === "backtests" ? (
        <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
          <Panel>
            <PanelHeader title="Run a backtest" subtitle={canBacktest ? "Net of modelled costs" : "Pro and above"} />
            <PanelBody className="space-y-3">
              <Field label="Strategy" htmlFor="bt-code">
                <Select id="bt-code" value={backtestCode} onChange={(event) => setBacktestCode(event.target.value)}>
                  {library.map((strategy) => (
                    <option key={strategy.code} value={strategy.code}>
                      {strategy.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Instrument" htmlFor="bt-symbol">
                <Input id="bt-symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
              </Field>
              <Field label="Timeframe" htmlFor="bt-tf">
                <Select
                  id="bt-tf"
                  value={timeframe}
                  onChange={(event) => setTimeframe(event.target.value as typeof timeframe)}
                >
                  {TIMEFRAMES.map((tf) => (
                    <option key={tf} value={tf}>
                      {tf}
                    </option>
                  ))}
                </Select>
              </Field>
              <label className="flex items-center gap-2 text-xs text-paper-muted">
                <input
                  type="checkbox"
                  checked={walkForward}
                  onChange={(event) => setWalkForward(event.target.checked)}
                  className="h-3.5 w-3.5 accent-champagne-500"
                />
                Walk-forward validation
              </label>
              <Button fullWidth loading={busy} onClick={runBacktest} disabled={!canBacktest || !backtestCode}>
                {canBacktest ? "Run backtest" : "Upgrade to run backtests"}
              </Button>
              <p className="text-2xs leading-relaxed text-paper-faint">
                A backtest that looks good on one window proves very little. Use walk-forward and compare against a
                buy-and-hold baseline before drawing conclusions.
              </p>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader title="Backtest history" subtitle="Stored with the parameters and cost model used" />
            {backtests.loading ? (
              <div className="p-5">
                <Skeleton className="h-24 w-full" />
              </div>
            ) : backtests.data && backtests.data.backtests.length ? (
              <Table>
                <THead>
                  <TR>
                    <TH>Instrument</TH>
                    <TH>TF</TH>
                    <TH align="right">Net P&amp;L</TH>
                    <TH align="right">Trades</TH>
                    <TH align="right">Max DD</TH>
                    <TH>Status</TH>
                    <TH>Run</TH>
                  </TR>
                </THead>
                <TBody>
                  {backtests.data.backtests.map((run) => (
                    <TR key={run.id}>
                      <TD mono>{run.instrument_symbol}</TD>
                      <TD>{run.timeframe}</TD>
                      <TD align="right" mono>
                        <span className={Number(run.metrics.net_pnl ?? 0) >= 0 ? "text-gain" : "text-loss"}>
                          {signedMoney(Number(run.metrics.net_pnl ?? 0))}
                        </span>
                      </TD>
                      <TD align="right" mono>
                        {run.trades_count}
                      </TD>
                      <TD align="right" mono>
                        {run.metrics.max_drawdown_pct !== undefined ? percent(Number(run.metrics.max_drawdown_pct)) : "—"}
                      </TD>
                      <TD>
                        <StatusBadge status={run.status} />
                      </TD>
                      <TD>{dateTime(run.created_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : (
              <EmptyState title="No backtests yet" description="Run one on the left. Results are stored, not overwritten." />
            )}
          </Panel>
        </div>
      ) : null}

      {tab === "sessions" ? (
        <Panel>
          <PanelHeader title="Paper sessions" subtitle="Simulated execution, attributed to a strategy version" />
          {sessions.loading ? (
            <div className="p-5">
              <Skeleton className="h-24 w-full" />
            </div>
          ) : sessions.data && sessions.data.sessions.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>Instrument</TH>
                  <TH>TF</TH>
                  <TH align="right">Starting</TH>
                  <TH align="right">Equity</TH>
                  <TH>Status</TH>
                  <TH>Last tick</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {sessions.data.sessions.map((session) => (
                  <TR key={session.id}>
                    <TD mono>{session.instrument_symbol}</TD>
                    <TD>{session.timeframe ?? "—"}</TD>
                    <TD align="right" mono>
                      {money(session.starting_balance)}
                    </TD>
                    <TD align="right" mono>
                      {money(session.equity)}
                    </TD>
                    <TD>
                      <div className="flex items-center gap-1.5">
                        <StatusBadge status={session.status} />
                        <DemoBadge />
                      </div>
                    </TD>
                    <TD>{dateTime(session.last_tick_at)}</TD>
                    <TD align="right">
                      {session.status === "running" ? (
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="secondary" onClick={() => tick(session)} disabled={busy}>
                            Tick
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => stop(session)} disabled={busy}>
                            Stop
                          </Button>
                        </div>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState
              title="No paper sessions"
              description="Start one from the strategy library to attribute simulated orders."
            />
          )}
        </Panel>
      ) : null}

      <Dialog
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected?.name ?? "Strategy"}
        description={selected?.summary}
        wide
      >
        {detail ? (
          <div className="space-y-4">
            <KeyValue
              items={[
                { label: "Category", value: String(detail.category ?? "—") },
                { label: "Version", value: String(detail.version ?? "—"), mono: true },
                { label: "Status", value: <StatusBadge status={String(detail.status ?? "draft")} /> },
                { label: "Markets", value: ((detail.supported_markets as string[]) ?? []).join(", ") || "—" },
                { label: "Timeframes", value: ((detail.timeframes as string[]) ?? []).join(", ") || "—" },
              ]}
            />
            <SpecBlock title="Entry rules" value={detail.entry_rules} />
            <SpecBlock title="Exit rules" value={detail.exit_rules} />
            <SpecBlock title="Risk parameters" value={detail.risk_params} />
            <SpecBlock title="Data requirements" value={detail.data_requirements} />
            <SpecBlock title="Backtest methodology" value={detail.backtest_methodology} />
            {detail.known_limitations ? (
              <div>
                <p className="label mb-1.5">Known limitations</p>
                <p className="text-xs leading-relaxed text-paper-muted">{String(detail.known_limitations)}</p>
              </div>
            ) : null}
          </div>
        ) : (
          <Skeleton className="h-40 w-full" />
        )}
      </Dialog>
    </div>
  );
}

function SpecBlock({ title, value }: { title: string; value: unknown }) {
  if (value === null || value === undefined) return null;
  return (
    <div>
      <p className="label mb-1.5">{title}</p>
      <pre className="overflow-x-auto rounded-lg border border-line-soft bg-ink-900 p-3 text-2xs leading-relaxed text-paper-muted">
        {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
