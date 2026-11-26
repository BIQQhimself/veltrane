# Known limitations

Written to be read by someone deciding whether to trust this build. Each item is something a
competent reviewer would find, so it is cheaper to state it here.

## Product

1. **The web app is working software, not a finished product.** `frontend/` is a Next.js 15 app
   with twelve workspace screens, onboarding and an admin console that talks to this API, and it is
   installable as a PWA. It has not been through design QA on real devices, has no localisation,
   no end-to-end browser tests in CI, and only a thin unit suite (chart scale invariants).
2. **No AI model is wired in.** The strategy library is deterministic (trend following, mean
   reversion, breakout, momentum rotation) and clearly labelled as such. "AI strategy generation"
   is a feature flag with no implementation behind it. No LLM is called anywhere, so there is no
   AI cost per subscriber yet — the analytics field exists and reads zero.
3. **Onboarding is a guided flow over API endpoints.** `/app/onboarding` walks the ten steps and
   records progress on `users.onboarding_step`, but several steps are explanatory rather than
   enforced: skipping them does not block paper trading, and only the live-trading checklist is
   hard-gated server-side.
4. **No native mobile app.** The web app is responsive and installable (manifest, maskable icons,
   standalone display, iOS `appleWebApp` metadata, safe-area padding), but there is no Capacitor or
   React Native shell, so there is nothing to submit to the App Store or Play Store yet.
5. **Single-user organisations.** The schema supports more seats; the API assumes one user per org.

## Trading

6. **No live exchange connectivity has been verified.** Binance, Bybit, OKX and Deriv adapters are
   implemented but unverified against real accounts. They are marked `implemented_unverified` in
   INTEGRATIONS.md, and the platform flag keeps live execution off.
7. **Deriv execution is verified only against a mock gateway.** Personal Access Token auth, OTP
   trading sockets, proposals, buy/sell, close and reconciliation are implemented and covered by
   integration tests against `tests/support/deriv_mock.py` plus end-to-end runner tests, but no
   funded Deriv account has been used. Until one is, the adapter stays `implemented_unverified` and live contracts stay
   behind the platform switch. Public market data and pricing are verified against the live
   gateway. The autotrade runner ships one deterministic baseline strategy (EMA cross with an RSI
   filter); it is not a profitable strategy and no performance claim is made.
8. **Stocks, futures and commodities are not covered.** Instruments exist in the schema; there is
   no equities broker adapter.
9. **Order types are limited** to market and limit. Stop orders are modelled as a stop price on the
   order, not as a separate venue order.
10. **No partial fills on paper.** A simulated order fills fully at one price with modelled slippage.
11. **Funding is a modelled input**, not fetched per position. Backtests accept a funding rate
    assumption rather than historical funding data.
12. **The backtest engine is event-loop simple.** One instrument, one timeframe, no multi-asset
    portfolio effects, no borrow costs for shorts, no corporate actions. It is honest about costs
    (fees, spread, slippage) but it is not a research platform.
13. **The scheduler is an in-process thread, not a durable worker.** `app/services/scheduler.py`
    ticks every running paper session once a minute inside the API process, which is enough for a
    single-node deployment and is surfaced in `/admin/system/health`. It does not survive a crash
    mid-tick, it does not coordinate across replicas (run exactly one scheduler-enabled instance),
    and it has no queue, retry or dead-letter handling. A durable worker (Celery, RQ or a cron
    container) is required before running more than one API replica. Live execution never runs
    from the scheduler: it only advances paper sessions.
14. **No portfolio optimiser.** The flag exists; the maths does not.
15. **Slippage estimate versus actual** is recorded per trade, but for paper trades the "actual" is
    the model's own output — it validates the pipeline, not the model's accuracy.
    The risk-budget strip on the terminal is likewise a mirror, not a gate:
    `/trading/risk-budget` recomputes the headroom of the blocking rules for display, sharing the
    arithmetic but not the code path. If the two ever diverge the risk engine still decides, and a
    test pins the daily-loss case. It reports paper figures only — live headroom depends on venue
    balances that are not verified.
16. **Demo history is generated, not historical.** `backend/scripts/seed_demo.py` writes the demo
    account's contracts and trades from the deterministic feed, with entry prices at open and exit
    prices at expiry, so the numbers are internally consistent — but they are a fixture, not a
    record of a real strategy trading real markets. Every demo row is flagged `is_demo` and labelled
    "simulated" in the interface.

## Billing

17. **Stripe is untested against a live account.** The webhook verification path is shared with the
    mock provider and covered by tests, but no real Stripe event has been received.
18. **No crypto payment processor or bank transfer rail.** The abstraction is ready; the adapters
    are not written.
19. **No dunning sequence.** A failed payment notifies once and starts a 7-day grace period.
20. **Tax is a single line item** with no jurisdiction rules. Real invoicing needs a tax engine.
21. **Performance fees are disabled by design** and require a legal review that has not happened.

## Security and operations

22. **No independent security review or penetration test.**
23. **MFA is optional**, including for staff. It should be mandatory before launch.
24. **No WAF, CAPTCHA or IP reputation.** Rate limits and lockout are the only brute-force controls.
25. **Redis loss re-enables revoked access tokens** until they expire (≤ 15 minutes).
26. **No point-in-time recovery.** Nightly logical backups only; worst-case loss is 24 hours.
27. **Email is an outbox.** Without SMTP settings nothing is delivered, so verification links must be
    read from the database in development.
28. **Migrations are checked for schema parity, not for data safety.**
    `tests/test_migrations.py` runs `alembic upgrade head` against a scratch database and compares
    it to the ORM metadata, so a missing column is caught. It does not test backfills, long-running
    locks or downgrades on a populated database, and most other tests still build their schema with
    `create_all`.
29. **No load or performance testing.** No numbers exist for throughput or latency under load, and
    none are claimed. The one background thread added for the paper scheduler has not been profiled
    against a large number of open sessions.
30. **No anomaly detection** beyond static fraud signals (multiple accounts per IP, repeated failed
    payments, unusual order bursts).

## Regulatory and commercial

31. **No regulatory review.** Operating a trading tool for retail users has jurisdiction-specific
    obligations (advice versus tooling, marketing claims, performance-fee rules). None of that work
    is done.
32. **No terms of service or privacy policy drafted here.** The registration endpoint records
    acceptance of a version string; the documents themselves do not exist in this repository.
33. **No trademark or domain clearance** for the VELTRANE name.
34. **No support staffing model.** The ticket workflow exists; the humans do not.
35. **Cost estimates in DEPLOYMENT.md are list-price arithmetic**, not quotes.

## Deployment (Render free tier)

36. **The Render blueprint is prepared, not deployed.** `render.yaml` defines the free-tier
    topology (static site + web service + Postgres) and `DEPLOYMENT_RENDER.md` documents the
    custom-domain and HTTPS steps for `corvex.fun`. Nothing in this repository has been deployed to
    Render and no domain has been connected.
37. **Email delivery is implemented but unverified.** `backend/app/services/email.py` supports a
    local outbox (default: records and sends nothing) and Resend. No Resend account has been
    configured here, so no message has been delivered to a real inbox and no `email.delivered`
    webhook has been observed. Until that happens, verification and reset mail in a real
    deployment depends on the operator setting `VELTRANE_EMAIL_PROVIDER=resend` and a verified
    sender. The outbox never marks anything sent that the provider did not accept.
38. **Free Render Postgres expires 30 days after creation** and has no managed backups. It is
    suitable for a preview, not for data you would miss.
39. **No Redis on the free tier by default.** Rate limiting and market-data caching become
    per-process. Kill switches, entitlements and the live-trading gates are database-backed and
    unaffected, but a multi-instance deployment would need shared Redis for limiter accuracy.
40. **Free web services sleep when idle.** The paper-session scheduler only ticks while the
    instance is awake, and the first request after a sleep waits 30–60 seconds (the browser client
    retries `502/503/504` twice before showing an error).
41. **The live-trading master switch is a staff control, not a launch action.** An Owner/Admin can
    disable live trading at any time, but cannot enable it unless the operator has also set
    `VELTRANE_LIVE_TRADING_ENABLED=true`, and no verified live adapter exists.

42. **Deriv OAuth has not been exercised against Deriv.** The authorisation-code + PKCE flow,
    state handling, account switch and encrypted credential creation are covered by tests against
    the local protocol mock, but no real Deriv application has completed the round trip. Deriv
    issues no refresh token, so an expired token requires the user to reconnect; there is no
    background renewal.
43. **One Deriv connection follows one account by design.** A user holding both a demo and a live
    Deriv account switches between them on a single connection. This is a deliberate product
    rule, not an oversight, but it means a user cannot run demo and live strategies on the same
    Deriv authorisation at the same time.
44. **Referral commission is manual.** VELTRANE measures what it can observe (clicks,
    registrations, OAuth starts, connections) and labels everything else unverified. There is no
    Deriv partner API integration; an operator copies the verified figure from the partner
    statement. Treat reported commission as an accounting record, not a live feed.
45. **Performance-fee terms remain disabled** pending legal review (see `SUBSCRIPTIONS.md`), and
    referral commission is not netted against performance fees anywhere.

## What this build is good for

A foundation a small team can extend: the safety model, tenancy, billing state machine, risk engine
and audit trail are real and tested. It is not a product that can be sold tomorrow, and the gap
between the two is the list above.

## Seeded Deriv history

- `scripts/seed_deriv_history.py` walks the public API as the account owner would: open, then close
  each contract. The seeded rows are genuinely produced by the execution gate and the risk engine,
  but the *decision* to trade is the script's, not a strategy's, and every settlement is recorded as
  an owner-initiated early exit because that is what the sandbox supports.
- The mock gateway always sells a contract back at 92% of stake, so seeded history is loss-only and
  never expires on its own. Real Deriv contracts settle against the underlying's final price; that
  path (`record_settlement` from reconciliation) is exercised only by unit tests.
- Seeded history is capped at three contracts so that the consecutive-loss breaker (four losses)
  stays disengaged and a reviewer can still place a trade.
