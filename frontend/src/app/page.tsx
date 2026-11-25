"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Fingerprint,
  Gauge,
  KeyRound,
  Layers,
  LineChart,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { money } from "@/lib/format";
import { Monogram, Wordmark } from "@/components/brand";
import { DemoTape } from "@/components/marketing/demo-tape";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Plan } from "@/lib/types";

const PILLARS = [
  {
    icon: ShieldCheck,
    title: "An independent risk engine",
    body: "Strategies propose. The risk engine decides. Position, exposure, leverage, drawdown, stop-loss, stale data and duplicate-order checks run before anything reaches a venue — and a refusal is stored, not swallowed.",
  },
  {
    icon: LineChart,
    title: "Every trade, fully inspectable",
    body: "Each fill opens an immutable record: entry reason, strategy version, every risk check with its result, fees, slippage estimate against actual, and net P&L after costs.",
  },
  {
    icon: KeyRound,
    title: "Your accounts, your funds",
    body: "VELTRANE never custodies money. You connect your own exchange or broker, trading-only permissions, credentials encrypted with envelope encryption and never returned through the API.",
  },
];

const STEPS = [
  ["01", "Connect read-only", "Point VELTRANE at an exchange with trading disabled. Balances and positions sync; nothing can move."],
  ["02", "Simulate with real rules", "Paper trading runs the same risk engine as live, on labelled demo data, with the same fee and slippage model."],
  ["03", "Authorise deliberately", "Live execution needs an eligible plan, a checklist, MFA and a cooling-off period. Then an operator must open the platform gate."],
  ["04", "Intervene at any moment", "Pause a strategy, disable a venue, or halt the whole platform. Switches persist outside the app, so they still hold when it is closed."],
];

export default function LandingPage() {
  const plans = useApi<{ plans: Plan[] }>((signal) => api("/plans", { signal, retryOnAuth: false }));

  return (
    <div className="min-h-screen bg-ink-950">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-ink-800 focus:px-4 focus:py-2 focus:text-sm focus:text-paper"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 border-b border-line-soft/80 bg-ink-950/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4 sm:px-6">
          <Link href="/" aria-label="VELTRANE home" className="flex items-center gap-2">
            <Wordmark />
          </Link>
          <nav className="hidden items-center gap-7 text-xs text-paper-muted md:flex" aria-label="Primary">
            <a href="#platform" className="transition hover:text-paper">
              Platform
            </a>
            <a href="#discipline" className="transition hover:text-paper">
              Risk discipline
            </a>
            <a href="#pricing" className="transition hover:text-paper">
              Pricing
            </a>
            <a href="#honesty" className="transition hover:text-paper">
              What we do not promise
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/login">
              <Button variant="ghost" size="sm">
                Sign in
              </Button>
            </Link>
            <Link href="/register">
              <Button size="sm">
                Open an account
                <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="relative overflow-hidden border-b border-line-soft/70">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-[0.5]"
            style={{
              background:
                "radial-gradient(60% 50% at 75% 0%, rgba(200,169,106,0.10) 0%, rgba(10,14,22,0) 70%), radial-gradient(50% 40% at 10% 20%, rgba(60,90,140,0.18) 0%, rgba(10,14,22,0) 70%)",
            }}
          />
          <div className="relative mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:py-24">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="gold">Simulation first</Badge>
                <Badge tone="outline">No custody of funds</Badge>
              </div>
              <h1 className="mt-5 text-balance text-4xl font-light leading-[1.1] tracking-tight text-paper sm:text-5xl lg:text-6xl">
                Institutional discipline
                <span className="block text-champagne-300">for autonomous retail trading</span>
              </h1>
              <p className="mt-5 max-w-xl text-sm leading-relaxed text-paper-muted sm:text-base">
                VELTRANE runs strategies on accounts you already own — with a deterministic risk engine that can refuse
                any order, a complete record of every trade, and a halt that works whether or not the app is open.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link href="/register">
                  <Button size="lg">
                    Start with simulation
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/login">
                  <Button size="lg" variant="secondary">
                    Sign in
                  </Button>
                </Link>
              </div>
              <p className="mt-4 max-w-lg text-2xs leading-relaxed text-paper-faint">
                No performance figures appear on this page. Nothing here is a promise of profit, and past or simulated
                results do not indicate future returns.
              </p>

              <dl className="mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-line-soft pt-6">
                {[
                  ["0", "funds held"],
                  ["1", "engine that can refuse"],
                  ["100%", "of fills inspectable"],
                ].map(([value, label]) => (
                  <div key={label}>
                    <dt className="num text-2xl font-light text-paper">{value}</dt>
                    <dd className="mt-1 text-2xs uppercase tracking-label text-paper-faint">{label}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div className="space-y-4">
              <DemoTape />
              <div className="panel p-5">
                <div className="flex items-center justify-between">
                  <p className="label">Risk decision</p>
                  <Badge tone="loss">rejected</Badge>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-paper-muted">
                  <span className="text-paper">max_position_notional_pct</span> — order notional 18.4% of equity exceeds
                  the 10.0% limit. No venue was contacted.
                </p>
                <div className="mt-3 space-y-1.5 border-t border-line-soft pt-3">
                  {[
                    ["kill_switch", true],
                    ["instrument_active", true],
                    ["market_data_fresh", true],
                    ["stop_loss_present", true],
                    ["position_size", false],
                  ].map(([rule, passed]) => (
                    <div key={String(rule)} className="flex items-center justify-between text-2xs">
                      <span className="num text-paper-faint">{rule}</span>
                      <span className={passed ? "text-gain" : "text-loss"}>{passed ? "pass" : "fail"}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-2xs text-paper-faint">Illustrative decision record, not a live order.</p>
              </div>
            </div>
          </div>
        </section>

        <section id="platform" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <p className="label">Platform</p>
          <h2 className="mt-2 max-w-2xl text-2xl font-light text-paper sm:text-3xl">
            Built like a trading desk, priced like software
          </h2>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {PILLARS.map((pillar) => (
              <article key={pillar.title} className="panel p-5">
                <pillar.icon className="h-4 w-4 text-champagne-400" aria-hidden />
                <h3 className="mt-3 text-sm text-paper">{pillar.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-paper-muted">{pillar.body}</p>
              </article>
            ))}
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <article className="panel p-5">
              <Gauge className="h-4 w-4 text-champagne-400" aria-hidden />
              <h3 className="mt-3 text-sm text-paper">Net-of-cost accounting</h3>
              <p className="mt-2 text-xs leading-relaxed text-paper-muted">
                Fees, spread, slippage and funding are recorded per fill. Performance is reported after costs, because a
                gross curve is a story, not a result.
              </p>
            </article>
            <article className="panel p-5">
              <Layers className="h-4 w-4 text-champagne-400" aria-hidden />
              <h3 className="mt-3 text-sm text-paper">One abstraction, honest adapters</h3>
              <p className="mt-2 text-xs leading-relaxed text-paper-muted">
                Crypto venues first through CCXT, then retail forex and indices. Each provider reports its real
                capabilities; the interface never pretends two venues behave alike.
              </p>
            </article>
          </div>
        </section>

        <section id="discipline" className="border-y border-line-soft/70 bg-ink-900">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <p className="label">Risk discipline</p>
            <h2 className="mt-2 max-w-2xl text-2xl font-light text-paper sm:text-3xl">
              Four gates between an idea and your capital
            </h2>
            <ol className="mt-8 grid gap-4 md:grid-cols-2">
              {STEPS.map(([number, title, body]) => (
                <li key={number} className="panel flex gap-4 p-5">
                  <span className="num text-xs text-champagne-400">{number}</span>
                  <div>
                    <h3 className="text-sm text-paper">{title}</h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-paper-muted">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="pricing" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="label">Pricing</p>
              <h2 className="mt-2 text-2xl font-light text-paper sm:text-3xl">Capability, not promises</h2>
              <p className="mt-2 max-w-xl text-xs leading-relaxed text-paper-muted">
                Tiers unlock strategies, automation and higher configured limits. None of them unlock real-money
                execution on their own.
              </p>
            </div>
            <Badge tone="info">Prices from the live plan configuration</Badge>
          </div>

          <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {plans.loading
              ? [0, 1, 2, 3].map((index) => <div key={index} className="panel h-72 animate-pulse" />)
              : (plans.data?.plans ?? []).map((plan) => (
                  <article
                    key={plan.code}
                    className={`panel flex flex-col p-5 ${plan.code === "pro" ? "border-champagne-600/40" : ""}`}
                  >
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm text-paper">{plan.name}</h3>
                      {plan.code === "pro" ? <Badge tone="gold">popular</Badge> : null}
                    </div>
                    <p className="mt-1 text-2xs leading-relaxed text-paper-faint">{plan.tagline}</p>
                    <p className="num mt-4 text-3xl font-light text-paper">
                      {plan.price_monthly === 0 ? "Free" : money(plan.price_monthly, plan.currency, 0)}
                      {plan.price_monthly > 0 ? <span className="ml-1 text-2xs text-paper-faint">/ month</span> : null}
                    </p>
                    <ul className="mt-4 flex-1 space-y-1.5">
                      {(plan.features ?? []).slice(0, 6).map((feature) => (
                        <li key={feature} className="flex gap-2 text-2xs leading-relaxed text-paper-muted">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-champagne-500" aria-hidden />
                          {feature}
                        </li>
                      ))}
                    </ul>
                    <div className="mt-5">
                      <Link href={plan.price_monthly === 0 ? "/register" : "/register?plan=" + plan.code}>
                        <Button fullWidth variant={plan.code === "pro" ? "primary" : "secondary"} size="sm">
                          {plan.price_monthly === 0 ? "Create free account" : `Choose ${plan.name}`}
                        </Button>
                      </Link>
                    </div>
                  </article>
                ))}
          </div>
        </section>

        <section id="honesty" className="border-t border-line-soft/70">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr]">
              <div>
                <p className="label">Plainly stated</p>
                <h2 className="mt-2 text-2xl font-light text-paper sm:text-3xl">What we will not tell you</h2>
                <p className="mt-3 text-xs leading-relaxed text-paper-muted">
                  Trading carries risk of loss. Automation reduces the effort of executing a plan; it does not remove
                  the possibility that the plan is wrong.
                </p>
              </div>
              <ul className="space-y-3">
                {[
                  "That any strategy is guaranteed, or likely, to be profitable.",
                  "That a backtest predicts live results. Backtests are hypotheses with known biases.",
                  "That simulated trading is real trading. Demo activity is labelled everywhere it appears.",
                  "That a subscription authorises live execution. It does not; authorisation is separate and revocable.",
                ].map((line) => (
                  <li key={line} className="flex gap-3 border-b border-line-soft/60 pb-3 text-xs leading-relaxed text-paper-muted">
                    <Fingerprint className="mt-0.5 h-3.5 w-3.5 shrink-0 text-champagne-500" aria-hidden />
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section className="border-t border-line-soft/70 bg-ink-900">
          <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-4 py-12 sm:px-6 md:flex-row md:items-center">
            <div className="flex items-center gap-3">
              <Monogram className="h-9 w-9" />
              <div>
                <p className="text-sm text-paper">Start where it is safe: simulation.</p>
                <p className="text-2xs text-paper-faint">Connect read-only, run strategies, inspect every fill.</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/register">
                <Button>
                  Open an account
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/login">
                <Button variant="secondary">Sign in</Button>
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line-soft/70">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <Wordmark />
            <p className="mt-3 max-w-sm text-2xs leading-relaxed text-paper-faint">
              VELTRANE is a provisional brand name, subject to legal and domain clearance. This deployment is a
              development build: live trading is disabled platform-wide and no real-money order is submitted.
            </p>
          </div>
          <div>
            <p className="label">Product</p>
            <ul className="mt-2 space-y-1.5 text-2xs text-paper-muted">
              <li>
                <Link href="/app" className="transition hover:text-paper">
                  Workspace
                </Link>
              </li>
              <li>
                <Link href="/app/strategies" className="transition hover:text-paper">
                  Strategy library
                </Link>
              </li>
              <li>
                <Link href="/app/billing" className="transition hover:text-paper">
                  Plans and billing
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <p className="label">Transparency</p>
            <ul className="mt-2 space-y-1.5 text-2xs text-paper-muted">
              <li className="flex items-center gap-1.5">
                <Wallet className="h-3 w-3" aria-hidden /> No custody of subscriber funds
              </li>
              <li className="flex items-center gap-1.5">
                <BarChart3 className="h-3 w-3" aria-hidden /> Performance always net of costs
              </li>
              <li className="flex items-center gap-1.5">
                <ShieldCheck className="h-3 w-3" aria-hidden /> Risk engine independent of AI
              </li>
            </ul>
          </div>
        </div>
        <div className="border-t border-line-soft/60">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-2xs text-paper-faint sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p>© {new Date().getFullYear()} VELTRANE. Development build, not a regulated financial service.</p>
            <p>Nothing on this site is investment advice.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
