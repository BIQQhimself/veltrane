"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { money, percent, signedMoney } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorNote, KeyValue, Skeleton, Stat } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import Link from "next/link";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";

type SymbolRow = { symbol: string; trades: number; net_pnl: number; win_rate_pct: number };
type StrategyRow = { key: string; label: string; trades: number; net_pnl: number; win_rate_pct: number };
type Analytics = {
  advanced_unlocked: boolean;
  symbols: SymbolRow[];
  strategies: StrategyRow[];
  costs: { by_kind: Record<string, number>; total: number };
  sessions: { total: number; running: number };
  open_positions: number;
  net_pnl_total: number;
  note: string;
};

export default function AnalyticsPage() {
  const analytics = useApi<Analytics>((signal) => api("/analytics", { signal }));
  const data = analytics.data;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Attribution"
        title="Analytics"
        description="Where the money actually came from, after costs. Figures are computed from stored trades — nothing is estimated or projected."
        action={
          <Badge tone={data?.advanced_unlocked ? "gold" : "neutral"}>
            {data?.advanced_unlocked ? "advanced unlocked" : "core view"}
          </Badge>
        }
      />

      {analytics.error ? <ErrorNote message={analytics.error} onRetry={analytics.refetch} /> : null}

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {analytics.loading ? (
          <>
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
            <Skeleton className="h-[120px]" />
          </>
        ) : (
          <>
            <Stat
              label="Net P&L"
              value={signedMoney(data?.net_pnl_total ?? 0)}
              tone={(data?.net_pnl_total ?? 0) >= 0 ? "gain" : "loss"}
              hint="all closed trades"
            />
            <Stat label="Total costs" value={money(data?.costs.total ?? 0, "USD", 4)} hint="fees and funding" />
            <Stat label="Open positions" value={`${data?.open_positions ?? 0}`} hint="live and simulated" />
            <Stat
              label="Paper sessions"
              value={`${data?.sessions.running ?? 0} / ${data?.sessions.total ?? 0}`}
              hint="running / total"
            />
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="By instrument" subtitle="Net of recorded costs" />
          {analytics.loading ? (
            <div className="p-5">
              <Skeleton className="h-24 w-full" />
            </div>
          ) : data && data.symbols.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>Instrument</TH>
                  <TH align="right">Trades</TH>
                  <TH align="right">Win rate</TH>
                  <TH align="right">Net P&amp;L</TH>
                </TR>
              </THead>
              <TBody>
                {data.symbols.map((row) => (
                  <TR key={row.symbol}>
                    <TD mono>{row.symbol}</TD>
                    <TD align="right" mono>
                      {row.trades}
                    </TD>
                    <TD align="right" mono>
                      {percent(row.win_rate_pct, 1)}
                    </TD>
                    <TD align="right" mono>
                      <span className={row.net_pnl >= 0 ? "text-gain" : "text-loss"}>{signedMoney(row.net_pnl)}</span>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState title="No instrument history" description="Close a trade to populate attribution." />
          )}
        </Panel>

        <Panel>
          <PanelHeader title="By strategy version" subtitle="Manual trades are labelled, not hidden" />
          {analytics.loading ? (
            <div className="p-5">
              <Skeleton className="h-24 w-full" />
            </div>
          ) : data && data.strategies.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>Strategy</TH>
                  <TH align="right">Trades</TH>
                  <TH align="right">Win rate</TH>
                  <TH align="right">Net P&amp;L</TH>
                </TR>
              </THead>
              <TBody>
                {data.strategies.map((row) => (
                  <TR key={row.key}>
                    <TD>{row.label}</TD>
                    <TD align="right" mono>
                      {row.trades}
                    </TD>
                    <TD align="right" mono>
                      {percent(row.win_rate_pct, 1)}
                    </TD>
                    <TD align="right" mono>
                      <span className={row.net_pnl >= 0 ? "text-gain" : "text-loss"}>{signedMoney(row.net_pnl)}</span>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState title="No strategy attribution" description="Trades placed inside a paper session carry the strategy version." />
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Cost breakdown" subtitle="Every fee is a deduction from return" />
          <PanelBody>
            {data && Object.keys(data.costs.by_kind).length ? (
              <KeyValue
                items={Object.entries(data.costs.by_kind).map(([kind, amount]) => ({
                  label: kind.replace(/_/g, " "),
                  value: money(amount, "USD", 4),
                  mono: true,
                }))}
              />
            ) : (
              <p className="py-6 text-center text-xs text-paper-faint">No fees recorded yet.</p>
            )}
            <p className="mt-4 text-2xs leading-relaxed text-paper-faint">{data?.note}</p>
          </PanelBody>
        </Panel>

        {data && !data.advanced_unlocked ? (
          <Panel className="border-champagne-600/30">
            <PanelHeader title="Advanced analytics" subtitle="Pro and Elite" />
            <PanelBody className="space-y-3">
              <div className="flex items-center gap-2 text-sm text-paper">
                <Lock className="h-4 w-4 text-champagne-400" aria-hidden />
                Roll-ups, drawdown decomposition and per-session attribution
              </div>
              <p className="text-xs leading-relaxed text-paper-muted">
                The core view shows what is recorded. The advanced view adds regime splits and cost-adjusted
                expectancy per strategy — it does not add projections.
              </p>
              <Link href="/app/billing">
                <Button size="sm" variant="secondary">
                  Compare plans
                </Button>
              </Link>
            </PanelBody>
          </Panel>
        ) : (
          <Panel>
            <PanelHeader title="Reading these numbers" />
            <PanelBody className="space-y-3 text-xs leading-relaxed text-paper-muted">
              <p>
                A positive net figure over a small sample is noise, not evidence. Treat anything under a few hundred
                trades as unproven, and check the drawdown before the return.
              </p>
              <p>
                Costs are recorded per trade. Slippage is shown per trade in the detail view, so a strategy that only
                looks profitable before costs is visible as such.
              </p>
              <p className="text-paper-faint">
                Paper results and live results are separated everywhere in this product. Mixing them would flatter the
                numbers, which is the opposite of the point.
              </p>
            </PanelBody>
          </Panel>
        )}
      </div>
    </div>
  );
}
