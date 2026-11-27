"use client";

import * as React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { dateTime, price } from "@/lib/format";
import { CandleChart } from "@/components/charts/candles";
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

  const [lastRefresh, setLastRefresh] = React.useState<Date | null>(null);
  React.useEffect(() => {
    if (summary.data) setLastRefresh(new Date());
  }, [summary.data]);

  useInterval(() => summary.refetch(), 30_000);

  const closes = candles.data?.candles.map((candle) => candle.close) ?? [];
  const changePct = closes.length > 1 ? ((closes[closes.length - 1]! - closes[0]!) / closes[0]!) * 100 : null;
  const activeMarket = markets.find((market) => market.symbol === active);

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Coverage"
        title="Markets"
        description="Quotes come from public venue endpoints when a source is configured, and from the deterministic demo feed otherwise. Each quote says which it is."
        action={<Badge tone="info">{summary.data?.data_source_mode ?? "demo"} source</Badge>}
      />

      {summary.error ? <ErrorNote message={summary.error} onRetry={summary.refetch} /> : null}

      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[1.35fr_1fr]">
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
                  <TH className="hidden sm:table-cell">Class</TH>
                  <TH align="right">Price</TH>
                  <TH className="hidden md:table-cell">Source</TH>
                  <TH className="hidden md:table-cell">Session</TH>
                </TR>
              </THead>
              <TBody>
                {markets.map((market) => (
                  <TR key={market.symbol} onClick={() => setSelected(market.symbol)} selected={active === market.symbol}>
                    <TD mono>{market.symbol}</TD>
                    <TD className="hidden sm:table-cell">{market.asset_class ?? "—"}</TD>
                    <TD align="right" mono>
                      {typeof market.price === "number" ? price(market.price) : "—"}
                    </TD>
                    <TD className="hidden md:table-cell">
                      <Badge tone={market.is_demo ? "info" : "gain"}>{market.is_demo ? "demo" : market.source ?? "live"}</Badge>
                    </TD>
                    <TD className="hidden md:table-cell">{market.market_open ? "open" : "closed"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState title="No instruments available" description="Configure a market data source to populate this list." />
          )}
        </Panel>

        <Panel className="xl:sticky xl:top-20">
          <PanelHeader
            title={active}
            subtitle={
              candles.data
                ? `${candles.data.candles.length} candles${changePct === null ? "" : ` · ${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}% over window`}`
                : "Select an instrument"
            }
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
                <CandleChart
                  candles={candles.data?.candles ?? []}
                  height={230}
                  showEma
                  showCrosshair
                  ariaLabel={`${active} candlestick chart`}
                />
                <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line-soft pt-4">
                  <div>
                    <p className="label">Last</p>
                    <p className="num mt-1 text-sm text-paper">{price(closes[closes.length - 1]!)}</p>
                  </div>
                  <div>
                    <p className="label">High</p>
                    <p className="num mt-1 text-sm text-paper">{price(Math.max(...closes))}</p>
                  </div>
                  <div>
                    <p className="label">Low</p>
                    <p className="num mt-1 text-sm text-paper">{price(Math.min(...closes))}</p>
                  </div>
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line-soft pt-4 text-xs">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-paper-faint">Venue</dt>
                    <dd className="text-paper">{activeMarket?.venue ?? "demo"}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-paper-faint">Class</dt>
                    <dd className="text-paper">{activeMarket?.asset_class ?? "—"}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-paper-faint">Session</dt>
                    <dd className="text-paper">{activeMarket?.market_open ? "open" : "closed"}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-paper-faint">Bars</dt>
                    <dd className="num text-paper">{closes.length}</dd>
                  </div>
                </dl>
                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line-soft pt-4">
                  <Link
                    href={`/app/terminal?symbol=${encodeURIComponent(active)}`}
                    className="rounded-lg border border-gold-400/40 bg-gold-400/10 px-3 py-1.5 text-xs text-gold-600 transition hover:border-gold-300 hover:bg-gold-400/15"
                  >
                    Trade in terminal
                  </Link>
                  <p className="text-2xs text-paper-faint">
                    Candles show closes only; volume is not smoothed.
                  </p>
                </div>
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
            <p className="mt-2 text-sm text-paper">
              {lastRefresh ? dateTime(lastRefresh.toISOString()) : "Waiting for the first response"}
            </p>
            <p className="mt-1 text-2xs text-paper-faint">
              Time of the last successful response. Auto-refresh every 30 seconds while this page is open.
            </p>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
