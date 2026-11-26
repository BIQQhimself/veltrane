import type { Trade } from "@/lib/types";

type Snapshot = Record<string, unknown> | null | undefined;

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Stake of a fixed-odds contract, taken from the risk snapshot recorded when it was placed. */
export function contractStake(trade: Pick<Trade, "risk_snapshot">): number | null {
  const stake = number((trade.risk_snapshot as Snapshot)?.stake);
  return stake !== null && stake > 0 ? stake : null;
}

/**
 * What a fixed-odds contract returned: the early-exit sale price when it was closed before expiry,
 * otherwise the payout it settles for. Payout is an estimate until the venue settles the contract.
 */
export function contractReturn(trade: Pick<Trade, "risk_snapshot">): { value: number; settled: boolean } | null {
  const snapshot = trade.risk_snapshot as Snapshot;
  const soldFor = number(snapshot?.sold_for);
  if (soldFor !== null) return { value: soldFor, settled: true };
  const payout = number(snapshot?.payout);
  if (payout !== null) return { value: payout, settled: false };
  return null;
}
