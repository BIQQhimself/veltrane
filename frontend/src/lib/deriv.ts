import { api } from "@/lib/api";
import type { Connection, RiskDecision } from "@/lib/types";

export type DerivSymbol = {
  symbol: string;
  name: string;
  market: string;
  submarket: string;
  pip_size: number | null;
  exchange_is_open: boolean;
  suspended: boolean;
};

export type DerivTicker = {
  symbol: string;
  price: number;
  ts: number;
  source: string;
  age_seconds: number;
};

/** Raw Deriv proposal. `ask_price` is the cost and `payout` the terminal value. */
export type DerivProposal = {
  id: string;
  ask_price: number;
  payout: number;
  spot?: number | null;
  spot_time?: number | null;
  longcode?: string;
  contract_type?: string;
  date_expiry?: number | null;
  display_value?: string;
  validation_params?: { stake?: { min?: number; max?: number } };
};

export type DerivTerms = {
  duration_seconds: number | null;
  payout_pct: number;
  min_stake: number;
  max_stake: number;
  allowed_durations: number[];
  term?: string;
  allowed_terms?: string[];
  term_source?: string;
};

export type DerivContractFamily = {
  terms: string[];
  unverified_terms?: string[];
  expiry_types?: string[];
};

export type DerivContracts = {
  symbol: string;
  currency: string | null;
  available: boolean;
  contracts: Record<string, DerivContractFamily>;
  source: string;
  fetched_at?: string;
  error?: { code: string; message: string } | null;
  note?: string;
};

export type DerivGateCheck = { check: string; passed: boolean; message: string };

export type DerivGate = {
  scope: string;
  allowed: boolean;
  blocking_message?: string;
  checks?: DerivGateCheck[];
};

export type DerivAccount = {
  account_id: string;
  account_type?: string;
  currency?: string;
  balance?: number;
  is_virtual?: boolean;
};

export type DerivOpenContract = {
  contract_id: string;
  symbol?: string;
  contract_type?: string;
  buy_price?: number;
  payout?: number | null;
  profit?: number | null;
  is_virtual?: boolean;
  date_start?: number | null;
  date_expiry?: number | null;
  longcode?: string;
};

export type DerivSessionState = {
  state?: string;
  connected?: boolean;
  account_id?: string | null;
  is_virtual?: boolean | null;
  failure_count?: number;
  last_error?: string | null;
  last_connected_at?: string | null;
  scopes?: string[];
};

export type DerivConnectionStatus = {
  connection: {
    id: string;
    label: string;
    status: string;
    environment: string;
    account_id: string | null;
    account_type: string | null;
    currency: string | null;
    is_demo: boolean;
    last_sync_at: string | null;
    last_auth_error: string | null;
    accounts: DerivAccount[];
    nickname: string;
  };
  session: DerivSessionState;
  gate: DerivGate;
  open_contracts: DerivOpenContract[];
  contracts_error: string;
  app_id: string;
};

export type DerivPreview = {
  proposal: DerivProposal;
  terms: DerivTerms;
  gate: DerivGate;
  scope: string;
  is_demo: boolean;
  note: string;
};

export type DerivOrder = {
  id: string;
  status: string;
  symbol: string;
  side: string;
  price: number | null;
  fee: number;
  fee_currency: string | null;
  provider_order_id: string | null;
  is_demo: boolean;
  mode: string;
  submitted_at: string | null;
  filled_at: string | null;
  rejection_reason: string | null;
  meta: Record<string, unknown>;
};

export type DerivOrderResult = {
  approved: boolean;
  order: DerivOrder;
  risk: RiskDecision | null;
  venue?: {
    contract_id: string | null;
    payout: number | null;
    balance_after: number | null;
    is_demo: boolean;
  };
  message?: string;
  idempotent_replay?: boolean;
};

export type DerivAutomation = {
  id: string;
  connection_id: string;
  enabled: boolean;
  mode: "approval" | "autonomous";
  symbol: string;
  contract_type: string;
  stake: number;
  duration: number;
  duration_unit: string;
  max_open_contracts: number;
  max_stake_per_trade: number;
  daily_loss_limit: number;
  daily_stake_limit: number;
  cooldown_seconds: number;
  signal_ttl_seconds: number;
  last_run_at: string | null;
  last_signal_at: string | null;
  halt_reason: string | null;
};

export type DerivSignal = {
  id: string;
  status: string;
  mode: string;
  symbol: string;
  side: string;
  contract_type: string;
  stake: number;
  duration: number;
  duration_unit: string;
  reason: string;
  risk_snapshot: Record<string, unknown> | null;
  order_id: string | null;
  contract_id: string | null;
  error: string | null;
  expires_at: string | null;
  created_at: string | null;
  decided_at: string | null;
};

export type DerivSymbols = {
  source: string;
  count: number;
  markets: Record<string, DerivSymbol[]>;
};

export type DerivTerm = { term: string; value: number; unit: string; label: string };

const UNIT_ORDER = ["t", "s", "m", "h", "d"];
const UNIT_NAMES: Record<string, [string, string]> = {
  t: ["tick", "ticks"],
  s: ["sec", "sec"],
  m: ["min", "min"],
  h: ["hour", "hours"],
  d: ["day", "days"],
};

/** Parse a venue term such as ``30s``. Anything else is refused rather than guessed at. */
export function parseTerm(raw: string): DerivTerm | null {
  const match = /^(\d+)([tsmhd])$/.exec(raw.trim());
  if (!match) return null;
  const value = Number(match[1]);
  const unit = match[2] as string;
  const [one, many] = UNIT_NAMES[unit] ?? ["", ""];
  return { term: raw.trim(), value, unit, label: `${value} ${value === 1 ? one : many}` };
}

/**
 * The venue's own duration menu. The list is whatever Deriv published for this symbol, so a
 * duration that the venue does not offer can never appear in the interface.
 */
export function venueTermOptions(
  contracts: Record<string, { terms?: string[] }> | undefined,
): DerivTerm[] {
  if (!contracts) return [];
  const seen = new Set<string>();
  const parsed: DerivTerm[] = [];
  for (const item of [...(contracts.CALL?.terms ?? []), ...(contracts.PUT?.terms ?? [])]) {
    const term = parseTerm(item);
    if (!term || seen.has(term.term)) continue;
    seen.add(term.term);
    parsed.push(term);
  }
  const rank = (unit: string) => UNIT_ORDER.indexOf(unit);
  return parsed.sort((a, b) => rank(a.unit) - rank(b.unit) || a.value - b.value);
}

export type DerivTermGroup = { unit: string; label: string; items: DerivTerm[] };

/** Group a menu for a grouped select control. */
export function groupTerms(options: DerivTerm[]): DerivTermGroup[] {
  return UNIT_ORDER.map((unit) => ({
    unit,
    label: UNIT_NAMES[unit]?.[1] ?? unit,
    items: options.filter((item) => item.unit === unit),
  })).filter((group) => group.items.length > 0);
}

export function derivConnections(connections: Connection[]): Connection[] {
  return connections.filter(
    (connection) => connection.provider === "deriv" && connection.status !== "revoked",
  );
}

export function fetchSymbols(refresh = false, signal?: AbortSignal) {
  return api<DerivSymbols>("/deriv/symbols", { query: { refresh }, signal });
}

export function fetchContracts(symbol: string, refresh = false, signal?: AbortSignal) {
  return api<DerivContracts>("/deriv/contracts", { query: { symbol, refresh }, signal });
}

export function fetchTicker(symbol: string, signal?: AbortSignal) {
  return api<DerivTicker>("/deriv/ticker", { query: { symbol }, signal });
}

export function fetchStatus(connectionId: string, signal?: AbortSignal) {
  return api<DerivConnectionStatus>(`/deriv/connections/${connectionId}/status`, { signal });
}

export function openSession(connectionId: string, action: "connect" | "reconnect" | "close") {
  return api<Record<string, unknown>>(`/deriv/connections/${connectionId}/session/${action}`, {
    method: "POST",
  });
}

export function previewContract(connectionId: string, body: Record<string, unknown>) {
  return api<DerivPreview>(`/deriv/connections/${connectionId}/preview`, { method: "POST", body });
}

export function openContract(connectionId: string, body: Record<string, unknown>) {
  return api<DerivOrderResult>(`/deriv/connections/${connectionId}/contracts`, {
    method: "POST",
    body,
  });
}

export function closeContract(connectionId: string, contractId: string) {
  return api<Record<string, unknown>>(
    `/deriv/connections/${connectionId}/contracts/${contractId}/close`,
    { method: "POST" },
  );
}

export function fetchAutomation(connectionId: string, signal?: AbortSignal) {
  return api<{ automation: DerivAutomation | null }>(
    `/deriv/connections/${connectionId}/automation`,
    { signal },
  );
}

export function saveAutomation(connectionId: string, body: Partial<DerivAutomation>) {
  return api<{ automation: DerivAutomation }>(`/deriv/connections/${connectionId}/automation`, {
    method: "PUT",
    body,
  });
}

export function fetchSignals(connectionId: string, status = "", signal?: AbortSignal) {
  return api<{ signals: DerivSignal[] }>(`/deriv/connections/${connectionId}/signals`, {
    query: { status },
    signal,
  });
}

export type SignalDecision = {
  approved?: boolean;
  signal?: DerivSignal;
  order?: { id?: string } | null;
  risk?: { decision?: string; failed_rules?: Array<{ code?: string; message?: string }> } | null;
};

export function decideSignal(signalId: string, decision: "approve" | "reject") {
  return api<SignalDecision>(`/deriv/signals/${signalId}/${decision}`, { method: "POST" });
}

export const MARKET_LABELS: Record<string, string> = {
  synthetic_index: "Synthetic indices",
  forex: "Forex",
  indices: "Stock indices",
  commodities: "Commodities",
  cryptocurrency: "Crypto",
};
