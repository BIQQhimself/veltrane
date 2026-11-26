# Database schema

PostgreSQL 17, SQLAlchemy 2.0 declarative models, Alembic migrations. **40 tables.**

Conventions:

- Primary keys are UUID strings (`Uuid(as_uuid=False)`), generated in Python, except for a few
  natural-key tables (`plans.code`, `feature_flags.key`, `system_settings.key`, `instruments.id`).
- Tenant-owned tables carry `org_id` with a foreign key to `organizations.id` and an index.
  Queries always filter on it.
- Money and quantities use `Numeric(24, 10)`; Python reads `Decimal`, serialisers cast to `float`
  at the HTTP boundary.
- Timestamps are `timestamptz` in UTC. `IdTimestampMixin` adds `id`, `created_at`, `updated_at`.
- JSON columns are JSONB.

## Identity and tenancy

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `organizations` | Tenant root | `name`, `slug`, `country`, `timezone`, `onboarding`, `is_demo`, `suspended`, `suspended_reason` |
| `users` | Subscriber or staff account | `email` unique, `password_hash`, `status`, `email_verified_at`, `mfa_enabled`, `mfa_secret_enc`, `mfa_recovery_hashes`, `is_staff`, `staff_role`, `token_version`, `failed_login_attempts`, `locked_until`, `last_login_at`, `onboarding_step`, `risk_profile`, `preferences`, `terms_accepted_at`, `terms_version`, `deleted_at` |
| `refresh_sessions` | Rotating refresh tokens | `jti` unique, `token_hash`, `expires_at`, `revoked_at`, `replaced_by`, `ip`, `user_agent` |
| `one_time_tokens` | Email verification and password reset | `purpose`, `token_hash`, `expires_at`, `used_at` |
| `email_outbox` | Queued mail | `to_email`, `subject`, `body`, `category`, `status`, `provider_message_id`, `error`, `sent_at` |
| `staff_invites` | Pending staff invitations | `email`, `role`, `invited_by`, `accepted_at` |

`token_version` increments on logout-all and on password change. A token carrying an older version
is rejected, which is how a global sign-out works without a per-request session lookup.

## Billing and entitlements

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `plans` | Tier catalogue, editable by owners | `code` PK, `name`, `tagline`, `price_monthly`, `currency`, `features`, `limits`, `sort_order`, `is_active`, `trial_days` |
| `subscriptions` | Current subscription per org | `plan_code`, `status`, `provider`, `provider_subscription_id`, `current_period_start/end`, `cancel_at_period_end`, `canceled_at`, `trial_end`, `seats`, `pending_plan_code`, `pending_effective_at` |
| `payments` | Provider payments | `provider`, `provider_payment_id`, `provider_invoice_id`, `amount`, `currency`, `status`, `idempotency_key`, `refunded_amount`, `receipt_url`, `raw` |
| `invoices` | Amounts owed | `number`, `subtotal`, `tax`, `total`, `currency`, `status`, `period_start/end`, `paid_at`, `line_items` |
| `refunds` | Staff-issued refunds | `payment_id`, `amount`, `currency`, `status`, `reason`, `provider_refund_id`, `created_by` |
| `webhook_events` | Raw webhook ledger, replay protection | `provider`, `event_id` (unique with provider), `event_type`, `payload`, `signature_valid`, `status`, `processed_at`, `error` |
| `entitlement_overrides` | Staff grant of a limit or feature | `key`, `value`, `reason`, `expires_at`, `created_by` |
| `performance_fee_records` | Elite performance fee calculations | `period_start/end`, `realized_pnl`, `hwm_before/after`, `fee_rate`, `fee_amount`, `currency`, `status`, `consent_id`, `calculation`, `notes` |
| `high_water_marks` | Per-org HWM | `scope`, `strategy_version_id`, `value`, `as_of` (unique on org+scope+strategy) |
| `fee_consents` | Signed consent records | `document_version`, `fee_rate`, `accepted_at`, `ip`, `snapshot`, `revoked_at` |
| `fees` | Any charged fee, including performance fees | `kind`, `amount`, `currency`, `reference_type`, `reference_id`, `detail`, `occurred_at` |

`webhook_events` is why a replayed provider event cannot double-grant: the unique
`(provider, event_id)` pair is checked before any state change.

## Connections and credentials

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `connections` | A linked exchange or broker account | `kind`, `provider`, `label`, `environment`, `status`, `permissions`, `capabilities`, `is_sandbox`, `last_sync_at`, `last_error`, `last_error_at`, `revoked_at`, `created_by` |
| `connection_credentials` | Envelope-encrypted secrets | `envelope` (JSONB: wrapped DEK, nonce, ciphertext), `kek_version`, `key_hint`, `fingerprint`, `rotated_at` |
| `balances` | Balance snapshot | `connection_id`, `asset`, `free`, `locked`, `total`, `usd_value`, `as_of` |
| `ledger_transactions` | Deposits, withdrawals and transfers as reported by the venue | `type`, `asset`, `amount`, `fee`, `reference_type`, `reference_id`, `external_id`, `occurred_at`, `meta` |

`connection_credentials` is the only table holding secret material, and it holds ciphertext plus a
masked hint and a SHA-256 fingerprint. No serializer reads `envelope`.

## Instruments and trading

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `instruments` | Normalised tradable instruments | `symbol`, `asset_class`, `venue`, `base`, `quote`, `tick_size`, `min_qty`, `contract_size`, `is_active` |
| `positions` | Position per instrument | `mode`, `connection_id`, `paper_session_id`, `instrument_symbol`, `side`, `quantity`, `avg_entry_price`, `mark_price`, `unrealized_pnl`, `realized_pnl`, `leverage`, `stop_loss`, `take_profit`, `strategy_version_id`, `status`, `opened_at`, `closed_at` |
| `orders` | Every order attempt, including rejects | `mode`, `connection_id`, `paper_session_id`, `instrument_symbol`, `side`, `order_type`, `quantity`, `price`, `stop_price`, `time_in_force`, `status`, `client_order_id`, `idempotency_key` (unique per org), `strategy_version_id`, `risk_decision_id`, `correlation_id`, `rejection_reason`, `submitted_at`, `filled_at`, `filled_qty`, `avg_fill_price`, `fee`, `fee_currency`, `slippage_est_bps`, `slippage_actual_bps`, `provider_order_id`, `is_demo` |
| `trades` | Immutable closed-trade record | `order_id`, `position_id`, `paper_session_id`, `mode`, `instrument_symbol`, `side`, `quantity`, `entry_price`, `exit_price`, `notional`, `fees`, `funding`, `slippage_est_bps`, `slippage_actual_bps`, `gross_pnl`, `net_pnl`, `entry_reason`, `exit_reason`, `strategy_version_id`, `risk_snapshot`, `is_demo`, `human_intervention`, `intervention_note`, `opened_at`, `closed_at` |
| `binary_contracts` | Fixed-odds (binary) contract, the paper instrument of the terminal | `user_id`, `paper_session_id`, `mode`, `instrument_symbol`, `asset_class`, `direction`, `stake`, `payout_pct`, `duration_seconds`, `entry_price`, `exit_price`, `price_source`, `is_demo`, `status`, `net_pnl`, `opened_at`, `expires_at`, `settled_at`, `risk_decision_id`, `trade_id` (set when settlement writes the trade), `strategy_version_id`, `source`, `entry_reason`, `rejection_reason`, `risk_snapshot`, `idempotency_key` |
| `risk_decisions` | One row per evaluated order | `order_intent`, `decision`, `failed_rules`, `checks`, `policy_id`, `policy_version`, `order_id`, `correlation_id` |
| `risk_policies` | Versioned rule sets | `org_id` (null = global), `name`, `version`, `rules`, `is_active`, `updated_by` |
| `trading_permissions` | Live authorisation state | `live_enabled`, `status`, `authorization_method`, `checklist`, `risk_acknowledged_at`, `mfa_verified_at`, `confirm_token_hash`, `confirm_expires_at`, `authorized_at`, `revoked_at`, `revoked_reason`, `jurisdiction`, `ip`, `user_agent` |
| `kill_switches` | Switch state per scope | `scope`, `target`, `engaged`, `reason`, `engaged_by`, `engaged_at`, `released_by`, `released_at` |
| `paper_sessions` | A simulated run of a strategy | `strategy_version_id`, `connection_id`, `instrument_symbol`, `timeframe`, `status`, `starting_balance`, `cash_balance`, `equity`, `config`, `last_tick_at`, `stopped_at` |

`trades` has no update path in the API. A manual close sets `human_intervention` and
`intervention_note` instead of editing prices or P&L.

## Strategies

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `strategies` | Strategy identity | `org_id` (null = system), `code` unique, `name`, `category`, `summary`, `is_system`, `enabled`, `created_by` |
| `strategy_versions` | Versioned configuration and rules | `strategy_id`, `version`, `status`, `supported_markets`, `timeframes`, `params_schema`, `default_params`, `entry_rules`, `exit_rules`, `risk_params`, `data_requirements`, `backtest_methodology`, `known_limitations`, `changelog`, `requires_approval`, `approved_by`, `approved_at` |
| `backtests` | A backtest run and its statistics | `strategy_version_id`, `instrument_symbol`, `timeframe`, `start_at`, `end_at`, `params`, `cost_model`, `status`, `metrics`, `equity_curve`, `trades_count`, `data_source`, `engine_version`, `error`, `completed_at` |

Editing a strategy creates a new version. Promoting a version to `live` requires staff approval,
and a live strategy whose version changes needs fresh user approval before it may trade again.

## Operations

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `notifications` | In-app feed | `user_id`, `category`, `severity`, `title`, `body`, `data`, `read_at` |
| `audit_logs` | Action trail | `org_id`, `actor_user_id`, `actor_email`, `actor_role`, `action`, `target_type`, `target_id`, `ip`, `user_agent`, `meta` |
| `support_tickets` | Subscriber requests | `user_id`, `subject`, `body`, `status`, `priority`, `messages` |
| `feature_flags` | Platform toggles | `key` PK, `enabled`, `description`, `rollout`, `updated_by` |
| `system_settings` | Singleton config | `key` PK, `value`, `description`, `updated_by` — cost model, performance-fee settings |
| `usage_metrics` | Metered usage | `metric`, `period` (date), `value`, `meta` (unique on org+metric+period) |
| `ai_usage` | Model calls for cost attribution | `model`, `purpose`, `tokens_in`, `tokens_out`, `cost_usd` |

`usage_metrics` enforces the five-demo-executions-per-day limit for Free. The increment happens in
the same transaction as the fill, so a crash cannot hand out a free extra execution.

## Migrations

`alembic/versions/142825588f8a_initial_schema.py` creates the whole schema. Later changes get their
own revision. Tests build the schema with `Base.metadata.create_all` for speed; production uses
Alembic, so the two must be kept in step. A drift test comparing Alembic head against the models
would be a worthwhile addition (see KNOWN_LIMITATIONS).

## Indexing notes

Hot paths and their indexes:

- Order submission: `orders(org_id, created_at desc)`, unique `orders(org_id, idempotency_key)`.
- Position limits: `positions(org_id, status)`.
- Trade history and P&L: `trades(org_id, created_at desc)`.
- Risk: `risk_policies(org_id, is_active)`, `risk_decisions(org_id, created_at desc)`.
- Metering: unique `usage_metrics(org_id, metric, period)`.
- Audit search: `audit_logs(org_id, created_at desc)`, `audit_logs(action)`.
- Webhooks: unique `webhook_events(provider, event_id)`.
