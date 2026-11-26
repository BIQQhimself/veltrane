"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Bot,
  ChevronRight,
  CircleDollarSign,
  Fingerprint,
  Gauge,
  KeyRound,
  Layers,
  LineChart,
  Lock,
  Menu,
  ShieldCheck,
  Timer,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";
import { Wordmark, BrandMark } from "@/components/brand";
import { MarketTape } from "@/components/marketing/market-tape";
import { CandleChart, type Candle } from "@/components/charts/candles";
import { cn } from "@/lib/cn";

/** Deterministic illustrative candles for the hero visual. Labelled as illustrative. */
function illustrativeCandles(seed: number, base: number, vol: number, count = 64): Candle[] {
  const candles: Candle[] = [];
  let price = base;
  let state = seed;
  const random = () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
  for (let i = 0; i < count; i += 1) {
    const drift = (random() - 0.47) * vol;
    const open = price;
    const close = Math.max(0.0001, open * (1 + drift));
    const high = Math.max(open, close) * (1 + random() * vol * 0.5);
    const low = Math.min(open, close) * (1 - random() * vol * 0.5);
    candles.push({
      ts: 1_700_000_000 + i * 900,
      open,
      high,
      low,
      close,
      volume: 40 + random() * 100,
    });
    price = close;
  }
  return candles;
}

const NAV = [
  { href: "#platform", label: "Platform" },
  { href: "#trading", label: "Trading" },
  { href: "#modes", label: "Modes" },
  { href: "#risk", label: "Risk" },
  { href: "#pricing", label: "Pricing" },
];

const PILLARS = [
  {
    icon: Timer,
    title: "Fixed-odds contracts, priced honestly",
    body: "Call or put, a duration you choose, a payout you can read before you commit. Stake is capped at open, and a losing contract pays nothing — the terminal says so on every ticket.",
  },
  {
    icon: ShieldCheck,
    title: "An independent risk engine",
    body: "Size, exposure, leverage, daily loss, drawdown, data staleness and duplicate orders are checked by a deterministic engine that the strategy layer cannot bypass.",
  },
  {
    icon: Bot,
    title: "A copilot that shows its work",
    body: "Trend, momentum, range position and volatility, with the reasoning and the invalidation level attached. No black-box signals, no implied certainty.",
  },
  {
    icon: Gauge,
    title: "Three modes, one kill switch",
    body: "Manual, AI-assisted and autonomous. Autonomous requires explicit activation, its own limits, and stops the moment you pull the switch — from any device.",
  },
];

const MODES = [
  {
    key: "manual",
    label: "Manual",
    icon: Fingerprint,
    headline: "You are the decision maker",
    body: "Full chart, full ticket, nothing pre-filled. Every contract passes the same risk checks as an automated one.",
    points: ["Chart, depth and payout in one view", "Stake guardrails before submit", "Immutable contract record"],
  },
  {
    key: "assisted",
    label: "AI-assisted",
    icon: Bot,
    headline: "Analysis on tap, execution on you",
    body: "The copilot reads the same candles you do and explains its bias. It cannot place a contract — that stays your click.",
    points: ["Bias with confidence and rationale", "Invalidation level stated up front", "Weight reduced on noise-dominated expiries"],
  },
  {
    key: "autonomous",
    label: "Autonomous",
    icon: Zap,
    headline: "Rules run while you are away",
    body: "Strategies trade inside limits you set, with a daily loss cap, an exposure cap and a global stop that works without the app open.",
    points: ["Explicit activation and consent record", "Per-strategy capital allocation", "Global and per-user kill switches"],
  },
];

const RISK_RULES = [
  "Maximum position and account exposure",
  "Daily loss and drawdown circuit breakers",
  "Stale market data rejection",
  "Duplicate order prevention",
  "Leverage ceilings where applicable",
  "Trading-session validation",
  "Per-provider trading disable",
  "Global kill switch",
];

const PLANS = [
  {
    name: "Free",
    price: "$0",
    cadence: "forever",
    blurb: "Read-only connections, portfolio analytics and simulated trading.",
    features: ["2 connected accounts", "5 simulated executions a day", "Market monitoring", "No real-money execution"],
    cta: "Start free",
    highlight: false,
  },
  {
    name: "Basic",
    price: "$19",
    cadence: "per month",
    blurb: "Core strategies and guardrailed automation.",
    features: ["3 connected accounts", "50 simulated executions a day", "Two-strategy library", "Paper automation"],
    cta: "Choose Basic",
    highlight: false,
  },
  {
    name: "Pro",
    price: "$49",
    cadence: "per month",
    blurb: "Backtesting, customisation and advanced analytics.",
    features: ["8 connected accounts", "250 simulated executions a day", "Backtesting and walk-forward", "Eligible for live after authorisation"],
    cta: "Choose Pro",
    highlight: true,
  },
  {
    name: "Elite",
    price: "$149",
    cadence: "per month",
    blurb: "Full library, portfolio optimisation, priority support.",
    features: ["25 connected accounts", "1,000 simulated executions a day", "Portfolio optimisation", "Optional performance-fee agreement"],
    cta: "Choose Elite",
    highlight: false,
  },
];

export default function MarketingPage() {
  const [open, setOpen] = React.useState(false);
  const heroCandles = React.useMemo(() => illustrativeCandles(97, 64200, 0.012), []);
  const secondaryCandles = React.useMemo(() => illustrativeCandles(41, 1.084, 0.0022, 48), []);
  const [mode, setMode] = React.useState("assisted");
  const activeMode = MODES.find((item) => item.key === mode) ?? MODES[1]!;

  return (
    <div className="min-h-screen bg-obsidian-950 text-paper">
      <header className="sticky top-0 z-40 border-b border-line-soft bg-obsidian-950/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-5 lg:px-8">
          <Link href="/" aria-label="VELTRANE home">
            <Wordmark />
          </Link>
          <nav className="hidden items-center gap-7 md:flex" aria-label="Primary">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="text-xs text-paper-muted transition-colors hover:text-paper"
              >
                {item.label}
              </a>
            ))}
          </nav>
          <div className="hidden items-center gap-2 md:flex">
            <Link
              href="/login"
              className="rounded-lg px-3 py-2 text-xs text-paper-muted transition-colors hover:text-paper"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              className="cta-gold inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-medium transition"
            >
              Open an account
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </div>
          <button
            type="button"
            className="rounded-lg border border-line-strong p-2 text-paper-muted md:hidden"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
        {open ? (
          <div className="border-t border-line-soft bg-obsidian-900 px-5 py-4 md:hidden">
            <nav className="grid gap-1" aria-label="Mobile">
              {NAV.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="rounded-lg px-2 py-2.5 text-sm text-paper-muted hover:bg-obsidian-800 hover:text-paper"
                >
                  {item.label}
                </a>
              ))}
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Link href="/login" className="rounded-lg border border-line-strong px-3 py-2.5 text-center text-sm">
                  Sign in
                </Link>
                <Link href="/register" className="cta-gold rounded-lg px-3 py-2.5 text-center text-sm font-medium">
                  Open account
                </Link>
              </div>
            </nav>
          </div>
        ) : null}
      </header>

      <main id="main">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 grid-bg opacity-70" aria-hidden />
          <div className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-electric-500/10 blur-[120px]" aria-hidden />
          <div className="relative mx-auto grid max-w-7xl gap-14 px-5 pb-16 pt-16 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:px-8 lg:pb-24 lg:pt-24">
            <div className="animate-fade-up">
              <span className="chip">
                <span className="h-1.5 w-1.5 rounded-full bg-gain" aria-hidden />
                Paper trading live · live routing gated
              </span>
              <h1 className="mt-6 font-display text-4xl font-semibold leading-[1.05] tracking-tight text-paper sm:text-5xl lg:text-6xl">
                Trade with an
                <span className="block bg-gradient-to-r from-platinum via-gold-300 to-gold-500 bg-clip-text text-transparent">
                  instrument, not a guess.
                </span>
              </h1>
              <p className="mt-6 max-w-xl text-sm leading-relaxed text-paper-muted sm:text-base">
                VELTRANE is a precision terminal for crypto, forex, equities and metals. Fixed-odds
                contracts with the payout in plain sight, an independent risk engine on every order,
                and a copilot that explains its reasoning instead of promising outcomes.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  href="/register"
                  className="cta-gold inline-flex items-center gap-2 rounded-lg px-5 py-3 text-sm font-medium transition"
                >
                  Open a paper account
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 rounded-lg border border-line-strong bg-obsidian-850 px-5 py-3 text-sm text-paper transition hover:border-electric-600/60"
                >
                  <LineChart className="h-4 w-4 text-electric-300" aria-hidden />
                  Explore the terminal
                </Link>
              </div>
              <dl className="mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-line-soft pt-6">
                {[
                  ["4", "asset classes"],
                  ["14", "instruments"],
                  ["0", "custody of funds"],
                ].map(([value, label]) => (
                  <div key={label}>
                    <dt className="num text-2xl font-medium text-paper">{value}</dt>
                    <dd className="mt-1 text-2xs uppercase tracking-label text-paper-faint">{label}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div className="relative animate-fade-in">
              <div className="hero-frame p-4 sm:p-5">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <BrandMark className="h-5 w-5" />
                    <span className="font-mono text-xs text-paper">BTC/USDT</span>
                    <span className="rounded border border-line-strong px-1.5 py-px text-3xs uppercase tracking-label text-paper-faint">
                      illustrative
                    </span>
                  </div>
                  <div className="flex gap-1">
                    {["1m", "5m", "15m", "1h"].map((tf, index) => (
                      <span
                        key={tf}
                        className={cn(
                          "rounded px-2 py-1 text-3xs",
                          index === 2 ? "bg-electric-500/15 text-electric-300" : "text-paper-faint",
                        )}
                      >
                        {tf}
                      </span>
                    ))}
                  </div>
                </div>
                <CandleChart candles={heroCandles} height={260} livePrice={heroCandles.at(-1)?.close} />
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div className="rounded-lg border border-gain/30 bg-gain/10 px-3 py-2.5">
                    <p className="text-3xs uppercase tracking-label text-gain/80">Call · 5m</p>
                    <p className="num mt-1 text-lg font-medium text-gain">+80%</p>
                  </div>
                  <div className="rounded-lg border border-loss/30 bg-loss/10 px-3 py-2.5">
                    <p className="text-3xs uppercase tracking-label text-loss/80">Put · 5m</p>
                    <p className="num mt-1 text-lg font-medium text-loss">+80%</p>
                  </div>
                </div>
                <p className="mt-3 text-3xs leading-relaxed text-paper-faint">
                  Illustrative interface. Payout is what a winning contract pays; a losing contract
                  returns nothing. Not a forecast.
                </p>
              </div>
              <div className="absolute -left-4 -top-5 hidden w-52 rounded-xl border border-line bg-obsidian-900/95 p-3 shadow-lift lg:block">
                <p className="text-3xs uppercase tracking-label text-paper-faint">Risk engine</p>
                <p className="mt-1 flex items-center gap-1.5 text-xs text-gain">
                  <BadgeCheck className="h-3.5 w-3.5" aria-hidden /> 17 checks passed
                </p>
                <p className="mt-1 text-3xs text-paper-faint">Stake 100.00 · 0.4% of equity</p>
              </div>
            </div>
          </div>
          <MarketTape />
        </section>

        {/* Pillars */}
        <section id="platform" className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <div className="max-w-2xl">
            <p className="label">The platform</p>
            <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
              Built like an instrument, not a casino
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-paper-muted">
              Every screen exists to answer one question: what is my risk right now, and what will it
              cost me? VELTRANE shows the payout, the probability you are implicitly accepting and the
              checks that ran before anything was placed.
            </p>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {PILLARS.map((pillar) => (
              <article
                key={pillar.title}
                className="group relative overflow-hidden rounded-xl border border-line bg-obsidian-850 p-6 transition-colors hover:border-electric-600/50"
              >
                <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-electric-500/5 blur-2xl transition group-hover:bg-electric-500/10" aria-hidden />
                <pillar.icon className="h-5 w-5 text-electric-300" aria-hidden />
                <h3 className="mt-4 font-display text-lg font-medium text-paper">{pillar.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-paper-muted">{pillar.body}</p>
              </article>
            ))}
          </div>
        </section>

        {/* Trading experience */}
        <section id="trading" className="border-y border-line-soft bg-obsidian-900/40">
          <div className="mx-auto grid max-w-7xl gap-12 px-5 py-20 lg:grid-cols-[1fr_1.1fr] lg:items-center lg:px-8">
            <div>
              <p className="label">The terminal</p>
              <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                One ticket, every number that matters
              </h2>
              <p className="mt-4 text-sm leading-relaxed text-paper-muted">
                Choose an asset, a direction and a duration. The ticket prices the payout, shows the
                maximum loss before you commit, and holds the stake as collateral for the contract
                term. Settlement is automatic and each contract keeps its own audit trail.
              </p>
              <ul className="mt-6 space-y-3">
                {[
                  "Call/put ticket with live payout and potential return",
                  "Duration from 60 seconds to one hour, expiry aligned to the clock",
                  "Open contract countdown and settlement history",
                  "Every settled contract opens into a full risk and cost breakdown",
                ].map((item) => (
                  <li key={item} className="flex items-start gap-2.5 text-sm text-paper-muted">
                    <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-gain" aria-hidden />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="grid gap-3">
              <div className="rounded-xl border border-line bg-obsidian-850 p-4">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-paper">EUR/USD</span>
                  <span className="text-3xs uppercase tracking-label text-paper-faint">Forex · 15m</span>
                </div>
                <CandleChart candles={secondaryCandles} height={180} showVolume={false} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-line bg-obsidian-850 p-4">
                  <p className="label">Payout</p>
                  <p className="num mt-1 text-2xl text-paper">76%</p>
                  <p className="mt-2 text-3xs text-paper-faint">On a 250.00 stake → 190.00 profit if correct.</p>
                </div>
                <div className="rounded-xl border border-line bg-obsidian-850 p-4">
                  <p className="label">Max loss</p>
                  <p className="num mt-1 text-2xl text-loss">250.00</p>
                  <p className="mt-2 text-3xs text-paper-faint">Capped at the stake. No margin call, no negative balance.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Modes */}
        <section id="modes" className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-2xl">
              <p className="label">Trading modes</p>
              <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                Autonomy you can withdraw in one click
              </h2>
            </div>
            <div className="flex rounded-lg border border-line-strong bg-obsidian-850 p-1" role="tablist" aria-label="Trading modes">
              {MODES.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  role="tab"
                  aria-selected={mode === item.key}
                  onClick={() => setMode(item.key)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-2 text-xs transition",
                    mode === item.key
                      ? "bg-electric-500/15 text-electric-200 shadow-[inset_0_0_0_1px_rgba(46,123,255,0.35)]"
                      : "text-paper-faint hover:text-paper-muted",
                  )}
                >
                  <item.icon className="h-3.5 w-3.5" aria-hidden />
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-8 grid gap-6 rounded-2xl border border-line bg-gradient-to-br from-obsidian-850 to-obsidian-900 p-6 lg:grid-cols-[1.1fr_1fr] lg:p-10">
            <div>
              <h3 className="font-display text-2xl font-medium text-paper">{activeMode.headline}</h3>
              <p className="mt-3 max-w-lg text-sm leading-relaxed text-paper-muted">{activeMode.body}</p>
              <ul className="mt-6 grid gap-2.5">
                {activeMode.points.map((point) => (
                  <li key={point} className="flex items-center gap-2 text-xs text-paper-muted">
                    <span className="h-1 w-1 rounded-full bg-electric-400" aria-hidden />
                    {point}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-line bg-obsidian-950/70 p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs text-paper-muted">Autonomous guardrails</p>
                <span className="chip border-gain/30 text-gain">armed</span>
              </div>
              <div className="mt-4 space-y-3">
                {[
                  ["Daily loss limit", "3.0% of equity", 30],
                  ["Account exposure cap", "30.0%", 55],
                  ["Max open contracts", "5 of 5", 82],
                ].map(([label, value, width]) => (
                  <div key={label as string}>
                    <div className="flex items-baseline justify-between text-2xs">
                      <span className="text-paper-faint">{label}</span>
                      <span className="num text-paper-muted">{value}</span>
                    </div>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-obsidian-750">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-electric-500 to-gain"
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-4 border-t border-line-soft pt-3 text-3xs leading-relaxed text-paper-faint">
                Limits are enforced server-side by the risk engine. A strategy cannot raise them, and
                the kill switch works without the app open.
              </p>
            </div>
          </div>
        </section>

        {/* Risk */}
        <section id="risk" className="border-y border-line-soft bg-obsidian-900/40">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 lg:grid-cols-[1fr_1.2fr] lg:px-8">
            <div>
              <p className="label">Risk architecture</p>
              <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                The engine that says no
              </h2>
              <p className="mt-4 text-sm leading-relaxed text-paper-muted">
                The risk engine is separate code from the strategy engine, with no shared state and no
                override path. It evaluates every contract, records the outcome, and rejects anything
                that breaches policy — including orders produced by the platform&apos;s own strategies.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                {["Deterministic", "Auditable", "Server-side", "Fail-closed"].map((tag) => (
                  <span key={tag} className="chip">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            <ul className="grid gap-2 sm:grid-cols-2">
              {RISK_RULES.map((rule) => (
                <li
                  key={rule}
                  className="flex items-center gap-2 rounded-lg border border-line bg-obsidian-850 px-3 py-2.5 text-xs text-paper-muted"
                >
                  <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-gain" aria-hidden />
                  {rule}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Trust */}
        <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <div className="grid gap-4 md:grid-cols-3">
            {[
              {
                icon: Lock,
                title: "Your funds stay with your broker",
                body: "VELTRANE never takes custody. Connections are read-only until you separately authorise trading, and withdrawal permissions are refused.",
              },
              {
                icon: KeyRound,
                title: "Credentials sealed at rest",
                body: "Exchange keys are envelope-encrypted with a key that never touches the database, and are never returned by any API response.",
              },
              {
                icon: Layers,
                title: "Tenant isolation by construction",
                body: "Every query is scoped to your organisation at the data-access layer, and staff tooling cannot read subscriber secrets in plaintext.",
              },
            ].map((item) => (
              <article key={item.title} className="rounded-xl border border-line bg-obsidian-850 p-6">
                <item.icon className="h-5 w-5 text-gain" aria-hidden />
                <h3 className="mt-4 font-display text-base font-medium text-paper">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-paper-muted">{item.body}</p>
              </article>
            ))}
          </div>
          <p className="mt-8 rounded-xl border border-warn/25 bg-warn/[0.06] px-4 py-3 text-2xs leading-relaxed text-warn/90">
            Risk disclosure: fixed-odds contracts are high-risk instruments. Most short-dated
            contracts lose money after costs. Nothing on this site is investment advice, and no
            performance figure shown is a forecast. Live trading remains disabled until the
            operational, legal and security prerequisites in our production-readiness register are met.
          </p>
        </section>

        {/* Pricing */}
        <section id="pricing" className="border-t border-line-soft bg-obsidian-900/40">
          <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
            <div className="max-w-2xl">
              <p className="label">Subscriptions</p>
              <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                Pay for capability, not for hope
              </h2>
              <p className="mt-4 text-sm leading-relaxed text-paper-muted">
                Every plan includes the full risk engine and the audit trail. Higher tiers unlock more
                instruments, more simulation and deeper analysis — never a bypass of a safety control.
              </p>
            </div>
            <div className="mt-10 grid gap-4 lg:grid-cols-4">
              {PLANS.map((plan) => (
                <article
                  key={plan.name}
                  className={cn(
                    "relative flex flex-col rounded-xl border bg-obsidian-850 p-6",
                    plan.highlight ? "border-electric-500/50 shadow-glow" : "border-line",
                  )}
                >
                  {plan.highlight ? (
                    <span className="absolute -top-2.5 left-6 rounded-full bg-gold-400 px-2 py-0.5 text-3xs font-medium uppercase tracking-label text-ink-950">
                      Most chosen
                    </span>
                  ) : null}
                  <h3 className="font-display text-lg font-medium text-paper">{plan.name}</h3>
                  <p className="mt-1 text-2xs text-paper-faint">{plan.blurb}</p>
                  <p className="mt-5 flex items-baseline gap-1.5">
                    <span className="num text-3xl font-medium text-paper">{plan.price}</span>
                    <span className="text-2xs text-paper-faint">{plan.cadence}</span>
                  </p>
                  <ul className="mt-5 flex-1 space-y-2">
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-2xs text-paper-muted">
                        <BadgeCheck className="mt-px h-3.5 w-3.5 shrink-0 text-gain" aria-hidden />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/register"
                    className={cn(
                      "mt-6 inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-xs font-medium transition",
                      plan.highlight
                        ? "cta-gold"
                        : "border border-line-strong text-paper hover:border-electric-600/60",
                    )}
                  >
                    {plan.cta}
                  </Link>
                </article>
              ))}
            </div>
            <p className="mt-6 text-2xs text-paper-faint">
              Prices shown in USD. Billing is provider-verified server-side; a subscription is only
              activated after a signed payment confirmation. Performance fees, where offered, require a
              separate signed agreement and a high-water mark.
            </p>
          </div>
        </section>

        {/* CTA */}
        <section className="relative overflow-hidden border-t border-line-soft">
          <div className="pointer-events-none absolute inset-0 aurora opacity-60" aria-hidden />
          <div className="relative mx-auto flex max-w-5xl flex-col items-center px-5 py-20 text-center lg:px-8">
            <BrandMark className="h-12 w-12 animate-float" glow />
            <h2 className="mt-6 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
              Start in simulation. Earn the right to go live.
            </h2>
            <p className="mt-4 max-w-xl text-sm leading-relaxed text-paper-muted">
              Open an account, connect a broker read-only, and trade the full terminal against
              simulated capital. Live execution requires a completed safety checklist and explicit
              authorisation — for you, not for the platform.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link
                href="/register"
                className="cta-gold inline-flex items-center gap-2 rounded-lg px-5 py-3 text-sm font-medium transition"
              >
                Create your account
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
              <Link
                href="/login"
                className="inline-flex items-center gap-2 rounded-lg border border-line-strong bg-obsidian-900/70 px-5 py-3 text-sm text-paper transition hover:border-electric-600/60"
              >
                Sign in
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line-soft bg-obsidian-950">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8">
          <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div>
              <Wordmark />
              <p className="mt-4 max-w-xs text-2xs leading-relaxed text-paper-faint">
                VELTRANE is a trading technology provider. It does not hold client funds, does not
                manage portfolios, and does not guarantee outcomes.
              </p>
              <div className="mt-4 flex gap-2">
                <span className="chip">
                  <CircleDollarSign className="h-3 w-3" aria-hidden /> No custody
                </span>
                <span className="chip">
                  <TrendingUp className="h-3 w-3" aria-hidden /> Paper first
                </span>
              </div>
            </div>
            {[
              {
                title: "Platform",
                links: [
                  ["Trading terminal", "/app/terminal"],
                  ["Markets", "/app/markets"],
                  ["Strategies", "/app/strategies"],
                  ["Analytics", "/app/analytics"],
                ],
              },
              {
                title: "Company",
                links: [
                  ["Pricing", "#pricing"],
                  ["Risk policy", "/risk"],
                  ["Security", "/security"],
                  ["Status", "/status"],
                ],
              },
              {
                title: "Account",
                links: [
                  ["Sign in", "/login"],
                  ["Create account", "/register"],
                  ["Billing", "/app/billing"],
                  ["Support", "/app/support"],
                ],
              },
            ].map((column) => (
              <div key={column.title}>
                <p className="text-2xs uppercase tracking-label text-paper-faint">{column.title}</p>
                <ul className="mt-3 space-y-2">
                  {column.links.map(([label, href]) => (
                    <li key={label}>
                      <Link
                        href={href as Parameters<typeof Link>[0]["href"]}
                        className="text-xs text-paper-muted transition-colors hover:text-paper"
                      >
                        {label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-10 flex flex-col gap-3 border-t border-line-soft pt-6 text-2xs text-paper-faint sm:flex-row sm:items-center sm:justify-between">
            <p>© {new Date().getFullYear()} VELTRANE. All rights reserved.</p>
            <p className="flex items-center gap-2">
              <BarChart3 className="h-3.5 w-3.5" aria-hidden />
              Simulated results are not indicative of future performance.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
