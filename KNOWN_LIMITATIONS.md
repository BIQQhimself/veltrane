# Known limitations

Written to be read by someone deciding whether to trust this build. Each item is something a
competent reviewer would find, so it is cheaper to state it here.

## Product

1. **The web app is working software, not a finished product.** `frontend/` is a Next.js 15 app
   with twelve workspace screens, onboarding and an admin console that talks to this API, and it is
   installable as a PWA. It has not been through design QA on real devices and has no localisation.
   There is no scripted end-to-end journey (sign up → connect → trade) and no React component test
   runner; the unit suite covers chart invariants, validation, theme derivation and the watchlist,
   and `frontend/e2e/visual-audit.mjs` checks every route for overflow, WCAG AA contrast and console
   errors at three viewports, but nothing exercises a flow through the UI.
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

5a. **The one-minute floor is a platform decision, not a venue limit.** Deriv prices 15-second and
   tick contracts; VELTRANE refuses them at the catalogue, the request schema, the execution layer
   and the automation runner. If the product ever offers shorter contracts, `TradingRule`
   (`app/db/constants.py`) is the single constant to change, and `tests/test_duration_floor.py`
   lists every place that must keep agreeing with it.
5b. **The real-money daily allowance is enforced but has never been exercised against a venue.**
   `live_executions` is incremented after a real fill and checked by the risk engine before one.
   Only the demo counter has been driven end to end, because no funded account has been used.

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

17. **The duration menu costs a round trip of proposals.** Building a catalogue for one symbol
    asks Deriv to price every ladder term inside every published band (roughly forty proposals),
    so the first call for a symbol takes seconds and is cached for five minutes. The catalogue is
    built per symbol, not per connection, and a venue hiccup simply yields `available: false` for
    that symbol until the cache expires — the terminal then offers no duration and refuses to
    trade, which is the intended failure mode but is a visible wait for the trader.
18. **Only `CALL` and `PUT` are offered, though more is discoverable.** Deriv publishes
    `DIGITEVEN`, `DIGITODD` and others for the same symbols. They are collected by the provider
    and deliberately withheld from the menu: there is no settlement path for them, and offering a
    contract the platform cannot settle honestly would be worse than not offering it.
19. **A missing expiry price voids a contract.** Settlement refuses to reprice at "now", so a
    contract whose expiry price cannot be resolved is voided and the stake returned. That is the
    conservative choice, but it means a data gap produces a void rather than a result, and voids
    will need an operator report before the numbers can be reconciled against the venue.
20. **The venue terminal has not been used by a real trader.** The duration menu, preview and
    order path are covered against the protocol mock only. Nothing in this build has submitted a
    real-money contract, and the platform switch stays off.

## Billing

21. **Stripe is untested against a live account.** The webhook verification path is shared with the
    mock provider and covered by tests, but no real Stripe event has been received.
22. **SPay cannot be integrated yet.** Its published documentation exposes no server-side
    transaction lookup and no signed payment or renewal notifications, only a browser callback.
    Activating a plan on that signal would let any visitor grant themselves a paid tier, so the
    adapter is not written. Details and the two ways to unblock it are in `INTEGRATIONS.md`.
23. **No crypto payment processor or bank transfer rail.** The abstraction is ready; the adapters
    are not written.
24. **No dunning sequence.** A failed payment notifies once and starts a 7-day grace period.
25. **Tax is a single line item** with no jurisdiction rules. Real invoicing needs a tax engine.
26. **Performance fees are disabled by design** and require a legal review that has not happened.
26a. **The VIP price is a placeholder.** $349 is seeded so the tier can be tested end to end; the
    operator must set the real figure in the admin console before any customer sees it. Every tier
    price is a database row, so changing it does not require a deploy.
27. **One historical registration 500 in production was never explained by a traceback.** No log
    access was available. The endpoint now survives the two failure classes reachable in that path
    (a lost duplicate-insert race returns `409`, and a failing verification email is isolated in a
    savepoint) and reports a retryable `503` when the database is briefly unavailable, so the same
    request can no longer surface as an internal error. Recurrence should be investigated from the
    `unhandled_error` log line, which carries the request id.

## Security and operations

28. **No independent security review or penetration test.**
29. **MFA is optional**, including for staff. It should be mandatory before launch.
30. **No WAF, CAPTCHA or IP reputation.** Rate limits and lockout are the only brute-force controls.
31. **Redis loss re-enables revoked access tokens** until they expire (≤ 15 minutes).
32. **No point-in-time recovery.** Nightly logical backups only; worst-case loss is 24 hours.
33. **Email is an outbox.** Without SMTP settings nothing is delivered, so verification links must be
    read from the database in development.
34. **Migrations are checked for schema parity, not for data safety.**
    `tests/test_migrations.py` runs `alembic upgrade head` against a scratch database and compares
    it to the ORM metadata, so a missing column is caught. It does not test backfills, long-running
    locks or downgrades on a populated database, and most other tests still build their schema with
    `create_all`.
35. **No load or performance testing.** No numbers exist for throughput or latency under load, and
    none are claimed. The one background thread added for the paper scheduler has not been profiled
    against a large number of open sessions.
36. **No anomaly detection** beyond static fraud signals (multiple accounts per IP, repeated failed
    payments, unusual order bursts).

## Regulatory and commercial

37. **No regulatory review.** Operating a trading tool for retail users has jurisdiction-specific
    obligations (advice versus tooling, marketing claims, performance-fee rules). None of that work
    is done.
38. **No terms of service or privacy policy drafted here.** The registration endpoint records
    acceptance of a version string; the documents themselves do not exist in this repository.
39. **No trademark or domain clearance** for the VELTRANE name.
40. **No support staffing model.** The ticket workflow exists; the humans do not.
41. **Cost estimates in DEPLOYMENT.md are list-price arithmetic**, not quotes.

## Deployment (Render free tier)

42. **The Render blueprint is prepared, not deployed.** `render.yaml` defines the free-tier
    topology (static site + web service + Postgres) and `DEPLOYMENT_RENDER.md` documents the
    custom-domain and HTTPS steps for `corvex.fun`. Nothing in this repository has been deployed to
    Render and no domain has been connected.
43. **Email delivery is implemented but unverified.** `backend/app/services/email.py` supports a
    local outbox (default: records and sends nothing) and Resend. No Resend account has been
    configured here, so no message has been delivered to a real inbox and no `email.delivered`
    webhook has been observed. Until that happens, verification and reset mail in a real
    deployment depends on the operator setting `VELTRANE_EMAIL_PROVIDER=resend` and a verified
    sender. The outbox never marks anything sent that the provider did not accept. The default
    sender and reply-to addresses (`notifications@veltrane.app`, `support@veltrane.app`) are
    placeholders: replace them with addresses on a domain verified with the provider, or every
    message will be rejected for an unverified sender.
44. **Free Render Postgres expires 30 days after creation** and has no managed backups. It is
    suitable for a preview, not for data you would miss.
45. **No Redis on the free tier by default.** Rate limiting and market-data caching become
    per-process. Kill switches, entitlements and the live-trading gates are database-backed and
    unaffected, but a multi-instance deployment would need shared Redis for limiter accuracy.
46. **Free web services sleep when idle.** The paper-session scheduler only ticks while the
    instance is awake, and the first request after a sleep waits 30–60 seconds (the browser client
    retries `502/503/504` twice before showing an error).
47. **The live-trading master switch is a staff control, not a launch action.** An Owner/Admin can
    disable live trading at any time, but cannot enable it unless the operator has also set
    `VELTRANE_LIVE_TRADING_ENABLED=true`, and no verified live adapter exists.

48. **Deriv OAuth has not been exercised against Deriv.** The authorisation-code + PKCE flow,
    state handling, account switch and encrypted credential creation are covered by tests against
    the local protocol mock, but no real Deriv application has completed the round trip. Deriv
    issues no refresh token, so an expired token requires the user to reconnect; there is no
    background renewal.
49. **One Deriv connection follows one account by design.** A user holding both a demo and a live
    Deriv account switches between them on a single connection. This is a deliberate product
    rule, not an oversight, but it means a user cannot run demo and live strategies on the same
    Deriv authorisation at the same time.
50. **Referral commission is manual.** VELTRANE measures what it can observe (clicks,
    registrations, OAuth starts, connections) and labels everything else unverified. There is no
    Deriv partner API integration; an operator copies the verified figure from the partner
    statement. Treat reported commission as an accounting record, not a live feed.
51. **Performance-fee terms remain disabled** pending legal review (see `SUBSCRIPTIONS.md`), and
    referral commission is not netted against performance fees anywhere.
52. **A revoked access token stays valid while Redis is down.** Logout writes the token's `jti` to a
    Redis denylist; if Redis is unreachable the revocation is skipped (the failure is logged, and
    the request still succeeds) so a stolen access token survives until it expires. The access-token
    lifetime is short and refresh tokens are revoked in Postgres, but a fail-closed denylist is the
    correct end state. The test suite needs Redis running for this reason — see `TESTING.md`.
53. **The theme engine covers tokens, not layout.** An administrator can repaint surfaces, text,
    action colours, gains/losses and chart colours, and rename the product, but cannot change
    typography, spacing, component shapes or page structure. A handful of decorative gradients and
    shadows still carry literal colours and do not follow the palette.
54. **Theme changes are global, not per-tenant.** One palette applies to every subscriber, including
    the admin console. There is no per-organisation white-labelling, and no light theme beyond the
    stored `default_theme` hint.
55. **Contrast is reported, not enforced.** The appearance console measures body and button contrast
    and warns below 4.5:1, but publishing a low-contrast palette is still allowed. The shipped
    palette passes WCAG AA on every route and breakpoint (`npm run audit:visual`), but an
    administrator who repaints the platform can still publish a palette that does not.
56. **The visual audit has two blind spots.** Text inside `position: fixed` bars is not measured from
    pixels, because those bars stack over one another and a crop cannot be attributed to a single
    element; and text over a canvas or a live chart is measured against the frame that happened to be
    painted when the screenshot was taken. Both are worth a glance at the stored screenshots after a
    layout change.

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
