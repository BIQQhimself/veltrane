"use client";

import * as React from "react";
import { api } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { dateTime, money } from "@/lib/format";
import { AreaChart } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorNote, Skeleton } from "@/components/ui/data";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { Candle, Instrument } from "@/lib/types";

type Summary = { markets: Instrument[]; data_source_mode: string };
type Candles = { symbol: string; timeframe: string; candles: Candle[] };

const TIMEFRAMES = ["15m", "1h", "4h", "1d"] as const;

export default function MarketsPage() {
  const [selected, setSelected] = React.useState<string | null>(null);
  const [timeframe, setTimeframe] = React.useState<(typeof TIMEFRAMES)[number]>("1h");
  const summary = useApi<Summary>((signal) => api("/markets/summary", { signal }));
  const markets = summary.data?.markets ?? [];
  const active = selected ?? markets[0]?.symbol ?? "BTC/USDT";
  const candles = useApi<Candles>(
    (signal) =>
      api(`/markets/candles/${encodeURIComponent(active)}`, { signal, query: { timeframe, limit: 200 } }),
    [active, timeframe],
  );

  useInterval(() => summary.refetch(), 30_000);

  const closes = candles.data?.candles.map((candle) => candle.close) ?? [];

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Coverage"
        title="Markets"
        description="Quotes come from public venue endpoints when a source is configured, and from the deterministic demo feed otherwise. Each quote says which it is."
        action={<Badge tone="info">{summary.data?.data_source_mode ?? "demo"} source</Badge>}
      />

      {summary.error ? <ErrorNote message={summary.error} onRetry={summary.refetch} /> : null}

      <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <Panel>
          <PanelHeader title="Instruments" subtitle="Refreshed every 30 seconds" />
          {summary.loading ? (
            <div className="space-y-2 p-5">
              {[0, 1, 2, 3, 4].map((row) => (
                <Skeleton key={row} className="h-9 w-full" />
              ))}
            </div>
          ) : markets.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>Symbol</TH>
                  <TH>Class</TH>
                  <TH align="right">Price</TH>
                  <TH>Source</TH>
                  <TH>Session</TH>
                </TR>
              </THead>
              <TBody>
                {markets.map((market) => (
                  <TR key={market.symbol} onClick={() => setSelected(market.symbol)} selected={active === market.symbol}>
                    <TD mono>{market.symbol}</TD>
                    <TD>{market.asset_class ?? "—"}</TD>
                    <TD align="right" mono>
                      {typeof market.price === "number" ? money(market.price, "USD", market.price > 100 ? 2 : 5) : "—"}
                    </TD>
                    <TD>
                      <Badge tone={market.is_demo ? "info" : "gain"}>{market.is_demo ? "demo" : market.source ?? "live"}</Badge>
                    </TD>
                    <TD>{market.market_open ? "open" : "closed"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState title="No instruments available" description="Configure a market data source to populate this list." />
          )}
        </Panel>

        <Panel>
          <PanelHeader
            title={active}
            subtitle={candles.data ? `${candles.data.candles.length} candles` : "Select an instrument"}
            action={
              <div className="flex gap-1">
                {TIMEFRAMES.map((tf) => (
                  <button
                    key={tf}
                    type="button"
                    onClick={() => setTimeframe(tf)}
                    className={`rounded px-2 py-1 text-2xs transition ${
                      timeframe === tf ? "bg-ink-750 text-paper" : "text-paper-faint hover:text-paper"
                    }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            }
          />
          <PanelBody>
            {candles.loading ? (
              <Skeleton className="h-52 w-full" />
            ) : closes.length > 1 ? (
              <>
                <AreaChart
                  values={closes}
                  tone={closes[closes.length - 1]! >= closes[0]! ? "gain" : "loss"}
                  height={220}
                  ariaLabel={`${active} close price chart`}
                />
                <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line-soft pt-4">
                  <div>
                    <p className="label">Last</p>
                    <p className="num mt-1 text-sm text-paper">{money(closes[closes.length - 1]!, "USD", 5)}</p>
                  </div>
                  <div>
                    <p className="label">High</p>
                    <p className="num mt-1 text-sm text-paper">{money(Math.max(...closes), "USD", 5)}</p>
                  </div>
                  <div>
                    <p className="label">Low</p>
                    <p className="num mt-1 text-sm text-paper">{money(Math.min(...closes), "USD", 5)}</p>
                  </div>
                </div>
                <p className="mt-4 text-2xs text-paper-faint">
                  This view plots closes only. Volume is available in the API response and is not smoothed or
                  interpolated here.
                </p>
              </>
            ) : (
              <EmptyState title="No candles" description="The selected instrument has no candle history from this source." />
            )}
          </PanelBody>
        </Panel>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Panel>
          <PanelBody>
            <p className="label">Venues in scope</p>
            <p className="mt-2 text-sm text-paper">Binance · Bybit · OKX</p>
            <p className="mt-1 text-2xs text-paper-faint">Crypto first, through CCXT. Retail forex and indices follow.</p>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <p className="label">Data integrity</p>
            <p className="mt-2 text-sm text-paper">Stale quotes are rejected</p>
            <p className="mt-1 text-2xs text-paper-faint">
              The risk engine refuses orders when the quote is older than the freshness window.
            </p>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <p className="label">Last refresh</p>
            <p className="mt-2 text-sm text-paper">{dateTime(new Date().toISOString())}</p>
            <p className="mt-1 text-2xs text-paper-faint">Auto-refresh every 30 seconds while this page is open.</p>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
