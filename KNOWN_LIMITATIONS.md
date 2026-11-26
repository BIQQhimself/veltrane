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
7. **Deriv is a scaffold.** WebSocket token auth is not implemented; the adapter refuses trading.
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
13. **No strategy scheduler.** Paper sessions advance when ticked (`/paper-sessions/{id}/tick`).
    Nothing runs on a timer in this build, so "autonomous trading" is a capability of the engine,
    not a running service. A worker process is required before that claim can be made.
14. **No portfolio optimiser.** The flag exists; the maths does not.
15. **Slippage estimate versus actual** is recorded per trade, but for paper trades the "actual" is
    the model's own output — it validates the pipeline, not the model's accuracy.

## Billing

16. **Stripe is untested against a live account.** The webhook verification path is shared with the
    mock provider and covered by tests, but no real Stripe event has been received.
17. **No crypto payment processor or bank transfer rail.** The abstraction is ready; the adapters
    are not written.
18. **No dunning sequence.** A failed payment notifies once and starts a 7-day grace period.
19. **Tax is a single line item** with no jurisdiction rules. Real invoicing needs a tax engine.
20. **Performance fees are disabled by design** and require a legal review that has not happened.

## Security and operations

21. **No independent security review or penetration test.**
22. **MFA is optional**, including for staff. It should be mandatory before launch.
23. **No WAF, CAPTCHA or IP reputation.** Rate limits and lockout are the only brute-force controls.
24. **Redis loss re-enables revoked access tokens** until they expire (≤ 15 minutes).
25. **No point-in-time recovery.** Nightly logical backups only; worst-case loss is 24 hours.
26. **Email is an outbox.** Without SMTP settings nothing is delivered, so verification links must be
    read from the database in development.
27. **No schema-drift test** between Alembic head and the SQLAlchemy models. Tests use
    `create_all`, so a migration bug would not be caught by the suite.
28. **No load or performance testing.** No numbers exist for throughput or latency under load, and
    none are claimed.
29. **No anomaly detection** beyond static fraud signals (multiple accounts per IP, repeated failed
    payments, unusual order bursts).

## Regulatory and commercial

30. **No regulatory review.** Operating a trading tool for retail users has jurisdiction-specific
    obligations (advice versus tooling, marketing claims, performance-fee rules). None of that work
    is done.
31. **No terms of service or privacy policy drafted here.** The registration endpoint records
    acceptance of a version string; the documents themselves do not exist in this repository.
32. **No trademark or domain clearance** for the VELTRANE name.
33. **No support staffing model.** The ticket workflow exists; the humans do not.
34. **Cost estimates in DEPLOYMENT.md are list-price arithmetic**, not quotes.

## What this build is good for

A foundation a small team can extend: the safety model, tenancy, billing state machine, risk engine
and audit trail are real and tested. It is not a product that can be sold tomorrow, and the gap
between the two is the list above.
