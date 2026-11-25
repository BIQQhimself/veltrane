export type RiskCheck = {
  code: string;
  passed: boolean;
  message: string;
  severity?: string;
  detail?: Record<string, unknown>;
};

export type RiskDecision = {
  id?: string;
  decision: "approved" | "rejected" | string;
  policy_version?: number;
  failed_rules?: string[];
  checks: RiskCheck[];
  created_at?: string;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  org_id: string;
  status: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  is_staff: boolean;
  staff_role: string | null;
  onboarding_step: number;
  risk_profile: Record<string, unknown>;
  preferences: Record<string, unknown>;
  last_login_at: string | null;
  created_at: string | null;
  terms_version: string | null;
};

export type Entitlements = {
  plan_code: string;
  plan_name: string;
  status: string;
  limits: Record<string, number | boolean | string[]>;
  features: Record<string, boolean>;
  subscription: {
    plan_code: string;
    status: string;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
  } | null;
};

export type Order = {
  id: string;
  mode: "paper" | "live" | string;
  is_demo: boolean;
  symbol: string;
  side: "buy" | "sell" | string;
  order_type: string;
  quantity: number;
  price: number | null;
  stop_price: number | null;
  status: string;
  rejection_reason: string | null;
  filled_qty: number | null;
  avg_fill_price: number | null;
  fee: number | null;
  fee_currency: string | null;
  slippage_est_bps: number | null;
  slippage_actual_bps: number | null;
  strategy_version_id: string | null;
  connection_id: string | null;
  paper_session_id: string | null;
  created_at: string | null;
  filled_at: string | null;
  risk_decision: RiskDecision | null;
};

export type Trade = {
  id: string;
  order_id: string | null;
  mode: string;
  is_demo: boolean;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  notional: number;
  fees: number;
  funding: number;
  slippage_est_bps: number;
  slippage_actual_bps: number;
  gross_pnl: number;
  net_pnl: number;
  entry_reason: string;
  exit_reason: string;
  strategy_version_id: string | null;
  human_intervention: boolean;
  intervention_note: string | null;
  opened_at: string | null;
  closed_at: string | null;
};

export type Position = {
  id: string;
  mode: string;
  symbol: string;
  side: "long" | "short" | string;
  quantity: number;
  avg_entry_price: number;
  mark_price: number | null;
  unrealized_pnl: number;
  realized_pnl: number;
  leverage: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  strategy_version_id: string | null;
  status: string;
  connection_id: string | null;
  paper_session_id: string | null;
  opened_at: string | null;
  closed_at: string | null;
};

export type PaperSession = {
  id: string;
  strategy_version_id: string | null;
  connection_id: string | null;
  instrument_symbol: string;
  timeframe: string | null;
  status: string;
  starting_balance: number;
  cash_balance: number;
  equity: number;
  config: Record<string, unknown>;
  last_tick_at: string | null;
  stopped_at: string | null;
};

export type Connection = {
  id: string;
  provider: string;
  label: string;
  kind: string;
  environment: string;
  status: string;
  permissions: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  is_sandbox: boolean;
  is_simulated?: boolean;
  last_sync_at: string | null;
  last_error: string | null;
  created_at: string | null;
};

export type Balance = {
  asset: string;
  free: number;
  locked: number;
  total: number;
  usd_value: number;
  as_of: string | null;
  connection_id: string;
};

export type PortfolioOverview = {
  equity: {
    live_balance_usd: number;
    simulated_balance_usd: number;
    paper_equity_usd: number;
    total_usd: number;
    simulated_source?: "paper_session" | "venue_balances" | "none";
    unrealized_pnl: number;
    realized_pnl_net: number;
    fees_paid: number;
    currency: string;
  };
  connections: Connection[];
  balances: Balance[];
  positions: Position[];
  allocation: Array<{ label: string; value: number }>;
  paper_session: PaperSession | null;
  has_live_data: boolean;
  note: string;
};

export type Instrument = {
  symbol: string;
  asset_class?: string;
  venue?: string;
  price?: number;
  change_hint?: number | null;
  is_demo?: boolean;
  source?: string;
  market_open?: boolean;
};

export type Candle = {
  ts: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type Strategy = {
  code: string;
  name: string;
  category: string;
  summary: string;
  is_system: boolean;
  enabled: boolean;
  version?: string | null;
  status?: string | null;
  supported_markets?: string[];
  timeframes?: string[];
  risk_params?: Record<string, unknown>;
  known_limitations?: string | null;
  requires_approval?: boolean;
};

export type Backtest = {
  id: string;
  strategy_version_id: string | null;
  instrument_symbol: string;
  timeframe: string;
  start_at: string | null;
  end_at: string | null;
  status: string;
  metrics: Record<string, number | null>;
  equity_curve?: Array<{ ts: string; equity: number }> | null;
  trades_count: number;
  created_at: string | null;
};

export type Notification = {
  id: string;
  category: string;
  severity: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  read_at: string | null;
  created_at: string | null;
};

export type TradingState = {
  platform_live_enabled: boolean;
  kill_switches: Record<string, unknown>;
  live: {
    status: string;
    eligible: boolean;
    checklist_items: Record<string, string>;
    checklist?: Record<string, boolean>;
    risk_document_version?: string;
    authorized_at?: string | null;
    confirm_expires_at?: string | null;
    blockers?: string[];
  };
  paper_session: PaperSession | null;
  open_positions: Position[];
  demo_executions_today: number;
  data_source_mode: string;
};

export type Subscription = {
  subscription: {
    plan_code: string;
    plan_name: string;
    status: string;
    current_period_start: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    provider: string | null;
    pending_plan_code?: string | null;
  } | null;
  entitlements: Entitlements;
  plans: Plan[];
};

export type Plan = {
  code: string;
  name: string;
  tagline: string;
  price_monthly: number;
  currency: string;
  features: string[];
  limits: Record<string, number | boolean | string[]>;
  is_active: boolean;
  sort_order?: number;
};


export type AuditEntry = {
  id: string;
  action: string;
  actor_email: string | null;
  actor_role: string | null;
  target_type: string | null;
  target_id: string | null;
  meta: Record<string, unknown>;
  ip: string | null;
  created_at: string | null;
};

export type Paged<T> = {
  items: T[];
  total?: number;
  limit?: number;
  offset?: number;
};

export type NotificationsResponse = {
  notifications: Notification[];
  unread_count: number;
};

export type TradeDetail = Trade & {
  order?: Order | null;
  strategy?: {
    code: string;
    name: string;
    version: string;
    status: string;
    known_limitations: string | null;
  } | null;
  fees_breakdown?: Array<{ kind: string; amount: number; currency: string; detail: Record<string, unknown> | null; occurred_at: string | null }>;
  risk_snapshot?: Record<string, unknown> | null;
  cost_summary?: {
    gross_pnl: number;
    fees: number;
    funding: number;
    net_pnl: number;
    slippage_est_bps: number;
    slippage_actual_bps: number;
  } | null;
};

export type AdminOverview = {
  window_days: number;
  mrr: number;
  arr: number;
  revenue_by_tier: Record<string, number>;
  subscribers_by_tier: Record<string, number>;
  organizations: number;
  active_users: number;
  paid_subscribers: number;
  new_subscriptions: number;
  cancellations: number;
  churn_rate_pct: number;
  free_to_paid_conversion_pct: number;
  payments_collected: number;
  payment_failures: number;
  refunds: number;
  performance_fee_revenue: number;
  ai_cost: number;
  ai_cost_per_subscriber: number;
  infra_cost_per_subscriber: number;
  support_cost_per_subscriber: number;
  contribution_margin: number;
  contribution_margin_pct: number;
  open_support_tickets: number;
  demo_executions: number;
  live_trades: number;
  cost_model: Record<string, number>;
  note: string;
};
