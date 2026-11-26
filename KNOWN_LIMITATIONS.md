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

## What this build is good for

A foundation a small team can extend: the safety model, tenancy, billing state machine, risk engine
and audit trail are real and tested. It is not a product that can be sold tomorrow, and the gap
between the two is the list above.
