"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { bps, dateTime, money, signedMoney } from "@/lib/format";
import { contractReturn, contractStake } from "@/lib/contracts";
import { Badge, DemoBadge, StatusBadge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { KeyValue, Skeleton } from "@/components/ui/data";
import { Tabs } from "@/components/ui/dialog";
import type { TradeDetail } from "@/lib/types";
import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";
import * as React from "react";

export function TradeDetailDialog({ tradeId, onClose }: { tradeId: string | null; onClose: () => void }) {
  const [tab, setTab] = React.useState("overview");
  const { data, loading, error } = useApi<TradeDetail | null>(
    (signal) =>
      tradeId
        ? api<{ trade: TradeDetail }>(`/trades/${tradeId}`, { signal }).then((payload) => payload.trade)
        : Promise.resolve(null),
    [tradeId],
  );

  React.useEffect(() => {
    if (tradeId) setTab("overview");
  }, [tradeId]);

  if (!tradeId) return null;

  const decision = data?.risk_decision ?? data?.order?.risk_decision ?? null;
  const snapshot = data?.risk_snapshot ?? null;
  const costNote = typeof snapshot?.cost_note === "string" ? snapshot.cost_note : null;
  const stake = data ? contractStake({ risk_snapshot: snapshot }) : null;
  const contractPayoff = data ? contractReturn({ risk_snapshot: snapshot }) : null;

  return (
    <Dialog open onClose={onClose} title="Trade record" description="Immutable record of the closed trade, including costs and risk checks." wide>
      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : error ? (
        <p className="rounded-lg border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">{error}</p>
      ) : data ? (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="num text-lg text-paper">{data.symbol}</span>
                <Badge tone={data.side === "buy" ? "gain" : "loss"}>{data.side}</Badge>
                <StatusBadge status={data.mode} />
                {data.is_demo ? <DemoBadge /> : null}
              </div>
              <p className="mt-1 text-xs text-paper-faint">
                {dateTime(data.opened_at)} → {dateTime(data.closed_at)}
              </p>
            </div>
            <div className="text-right">
              <p className={`num text-xl ${data.net_pnl >= 0 ? "text-gain" : "text-loss"}`}>
                {signedMoney(data.net_pnl)}
              </p>
              <p className="text-2xs text-paper-faint">net of fees and funding</p>
            </div>
          </div>

          <Tabs
            tabs={[
              { id: "overview", label: "Overview" },
              { id: "costs", label: "Costs" },
              { id: "risk", label: "Risk checks", count: decision?.checks.length },
              { id: "context", label: "Entry & exit" },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "overview" ? (
            <div className="grid gap-5 sm:grid-cols-2">
              <KeyValue
                items={[
                  stake !== null
                    ? { label: "Stake", value: money(stake), mono: true }
                    : { label: "Quantity", value: data.quantity, mono: true },
                  { label: "Spot at entry", value: money(data.entry_price), mono: true },
                  stake !== null
                    ? {
                        label: contractPayoff?.settled ? "Sold for" : "Payout if won",
                        value: contractPayoff ? money(contractPayoff.value) : "—",
                        mono: true,
                      }
                    : { label: "Exit price", value: money(data.exit_price), mono: true },
                  { label: "Notional", value: money(data.notional), mono: true },
                  { label: "Gross P&L", value: signedMoney(data.gross_pnl), mono: true },
                  { label: "Net P&L", value: signedMoney(data.net_pnl), mono: true },
                ]}
              />
              <KeyValue
                items={[
                  { label: "Strategy", value: data.strategy ? `${data.strategy.name} v${data.strategy.version}` : "Manual" },
                  { label: "Strategy status", value: data.strategy ? <StatusBadge status={data.strategy.status} /> : "—" },
                  { label: "Order", value: <span className="num text-2xs">{data.order_id ?? "—"}</span> },
                  { label: "Human intervention", value: data.human_intervention ? <Badge tone="warn">Yes</Badge> : "No" },
                  { label: "Slippage estimate", value: bps(data.slippage_est_bps), mono: true },
                  { label: "Slippage actual", value: bps(data.slippage_actual_bps), mono: true },
                ]}
              />
            </div>
          ) : null}

          {tab === "costs" ? (
            <div className="space-y-4">
              <KeyValue
                items={[
                  { label: "Gross P&L", value: signedMoney(data.cost_summary?.gross_pnl ?? data.gross_pnl), mono: true },
                  { label: "Fees", value: money(data.fees, "USD", 4), mono: true },
                  { label: "Funding", value: money(data.funding, "USD", 4), mono: true },
                  { label: "Net P&L", value: signedMoney(data.net_pnl), mono: true },
                  { label: "Slippage estimated", value: bps(data.slippage_est_bps), mono: true },
                  { label: "Slippage actual", value: bps(data.slippage_actual_bps), mono: true },
                ]}
              />
              {data.fees_breakdown && data.fees_breakdown.length > 0 ? (
                <div>
                  <p className="label mb-2">Fee ledger</p>
                  <ul className="divide-y divide-line-soft/70 rounded-lg border border-line-soft">
                    {data.fees_breakdown.map((fee, index) => (
                      <li key={index} className="flex items-center justify-between px-3 py-2 text-xs">
                        <span className="text-paper-muted">{fee.kind}</span>
                        <span className="num text-paper">
                          {money(fee.amount, fee.currency, 4)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : costNote ? (
                <p className="rounded-lg border border-line-soft bg-obsidian-900/40 px-3 py-2 text-xs leading-relaxed text-paper-muted">
                  {costNote}
                </p>
              ) : (
                <p className="text-xs text-paper-faint">No separate fee rows recorded for this trade.</p>
              )}
            </div>
          ) : null}

          {tab === "risk" ? (
            <div className="space-y-3">
              {decision ? (
                <>
                  <div className="flex items-center justify-between rounded-lg border border-line-soft px-3 py-2">
                    <div className="flex items-center gap-2 text-xs">
                      {decision.decision === "approved" ? (
                        <CheckCircle2 className="h-4 w-4 text-gain" aria-hidden />
                      ) : (
                        <ShieldAlert className="h-4 w-4 text-loss" aria-hidden />
                      )}
                      <span className="text-paper">{decision.decision}</span>
                    </div>
                    <span className="text-2xs text-paper-faint">
                      policy v{decision.policy_version ?? "—"}
                    </span>
                  </div>
                  <ul className="divide-y divide-line-soft/70 rounded-lg border border-line-soft">
                    {decision.checks.map((check) => (
                      <li key={check.code} className="flex items-start justify-between gap-4 px-3 py-2">
                        <div className="min-w-0">
                          <p className="num text-2xs text-paper">{check.code}</p>
                          <p className="mt-0.5 text-xs text-paper-faint">{check.message}</p>
                        </div>
                        {check.passed ? (
                          <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gain" aria-label="passed" />
                        ) : (
                          <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-loss" aria-label="failed" />
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-xs leading-relaxed text-paper-faint">
                  No risk decision is stored for this row. Trades you place through the terminal record every
                  check the deterministic engine ran; older simulated rows backfilled by the demo seeder were
                  written straight to the ledger and never passed through it.
                </p>
              )}
            </div>
          ) : null}

          {tab === "context" ? (
            <div className="space-y-4">
              <div>
                <p className="label mb-1.5">Entry reason</p>
                <p className="rounded-lg border border-line-soft bg-ink-900 px-3 py-2 text-xs leading-relaxed text-paper-muted">
                  {data.entry_reason || "—"}
                </p>
              </div>
              <div>
                <p className="label mb-1.5">Exit reason</p>
                <p className="rounded-lg border border-line-soft bg-ink-900 px-3 py-2 text-xs leading-relaxed text-paper-muted">
                  {data.exit_reason || "—"}
                </p>
              </div>
              {data.human_intervention ? (
                <div className="rounded-lg border border-warn/30 bg-warn/5 px-3 py-2">
                  <p className="text-2xs uppercase tracking-label text-warn">Human intervention</p>
                  <p className="mt-1 text-xs text-paper-muted">{data.intervention_note || "No note recorded."}</p>
                </div>
              ) : null}
              {data.strategy?.known_limitations ? (
                <div>
                  <p className="label mb-1.5">Known limitations</p>
                  <p className="text-xs leading-relaxed text-paper-faint">{data.strategy.known_limitations}</p>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Dialog>
  );
}
