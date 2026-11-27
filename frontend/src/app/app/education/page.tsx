"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, BookOpen, Calculator, ChevronDown, Clock, ShieldCheck } from "lucide-react";
import { SectionHeading } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

type Lesson = {
  id: string;
  title: string;
  minutes: number;
  summary: string;
  body: string[];
};

const LESSONS: Lesson[] = [
  {
    id: "costs",
    title: "Why after-cost profit is the only profit that counts",
    minutes: 4,
    summary: "Spread, commission, swap and slippage are charged on every trade. A strategy that ignores them is fiction.",
    body: [
      "A Deriv multiplier or contract has a spread built into the entry price. A crypto order pays a taker fee. Overnight positions may pay swap or funding. Every one of those costs is real money leaving the account.",
      "A strategy that wins 60% of the time with a 1:1 payoff still loses if each trade costs more than the edge. That is why the platform reports net P&L after fees, spread, slippage and funding — and why a gross-profit curve alone is never shown as a result.",
      "Before you enable automation, read the cost line on a few of your own simulated trades. If the edge disappears after costs, the strategy has no edge.",
    ],
  },
  {
    id: "risk-per-trade",
    title: "Position size before entry, not after a loss",
    minutes: 5,
    summary: "Decide the maximum you can lose on a trade while you are calm. The risk engine enforces it when you are not.",
    body: [
      "Risk per trade is the distance to your stop multiplied by your size. On a $1,000 account, risking 1% means the maximum acceptable loss is $10 — not 'about $10'.",
      "The deterministic risk engine checks position size, account exposure, portfolio exposure, daily loss and drawdown before any order leaves the platform. It does not care how confident a signal is.",
      "If a signal cannot be expressed within your limits, it is rejected and the rejection is recorded. A rejected order is a working control, not a bug.",
    ],
  },
  {
    id: "drawdown",
    title: "Drawdown is the number that ends accounts",
    minutes: 4,
    summary: "A 50% loss needs a 100% gain to recover. Daily and overall limits exist to stop that arithmetic before it starts.",
    body: [
      "Losing 20% of an account requires a 25% gain to get back to even. Losing 50% requires 100%. The further you fall, the harder the recovery, and the more likely a trader abandons discipline.",
      "Set a daily loss limit and an overall drawdown limit you would accept on your worst day. The platform halts automation when either is hit, and it stays halted until you deliberately reset it.",
      "A halt is not a failure. It is the difference between a bad week and a closed account.",
    ],
  },
  {
    id: "session-vs-background",
    title: "Session automation vs background automation",
    minutes: 3,
    summary: "Knowing which mode is running tells you whether closing your laptop stops your strategies.",
    body: [
      "Session automation runs only while the platform is open. The workspace sends a heartbeat; when it stops, automation stops within a minute. It is the safest way to watch a strategy work.",
      "Background automation continues when you close the browser, within your plan's trade allowance and every risk rule. It is the mode that needs the most trust, so start it on a demo account first.",
      "Both modes are visible in the header and on the membership page. If the header shows a paused state, no automated order will be placed, whatever the strategy wants.",
    ],
  },
  {
    id: "kill-switch",
    title: "The kill switch is yours, and it works without the app",
    minutes: 2,
    summary: "One control stops every automated order for your organisation and records who flipped it and why.",
    body: [
      "The kill switch is enforced server-side. It does not depend on this tab staying open, and it cannot be bypassed by a strategy, a signal or an AI suggestion.",
      "Engaging it blocks new automated orders immediately. Existing positions are not closed for you — closing them is a decision only you should make.",
      "Every engage and release is written to the audit log with the reason you give. That record is what protects you if something goes wrong.",
    ],
  },
  {
    id: "live-authorisation",
    title: "What live trading requires, and why it is deliberately slow",
    minutes: 4,
    summary: "A paid plan makes you eligible. It does not switch on real money.",
    body: [
      "Live execution needs explicit authorisation from the account owner, a completed safety checklist, two-factor authentication, a verified connection with trading permission only, and a platform-wide enablement.",
      "We ask for trading permission and never for withdrawal access. VELTRANE cannot move your funds, and a compromised token cannot empty your account.",
      "If any precondition lapses — a disconnected account, an expired authorisation, a platform-wide disable — live orders stop. Paper trading is unaffected.",
    ],
  },
];

export default function EducationPage() {
  const [openId, setOpenId] = React.useState<string | null>("costs");

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Education"
        title="The parts of trading that decide the outcome"
        description="Short, plain lessons on costs, sizing, drawdown and the controls that exist to protect you. No signals, no promises, no shortcuts."
        action={
          <Link
            href="/app/terminal"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-2 text-2xs text-paper-muted transition hover:bg-obsidian-800 hover:text-paper"
          >
            Practise in the terminal
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <section className="space-y-3" aria-label="Lessons">
          {LESSONS.map((lesson) => {
            const open = openId === lesson.id;
            return (
              <article key={lesson.id} className={cn("tile transition", open && "border-line-strong")}>
                <button
                  type="button"
                  onClick={() => setOpenId(open ? null : lesson.id)}
                  aria-expanded={open}
                  className="flex w-full items-start justify-between gap-3 p-4 text-left"
                >
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2">
                      <BookOpen className="h-3.5 w-3.5 text-electric-300" aria-hidden />
                      <span className="text-xs font-medium text-paper">{lesson.title}</span>
                    </span>
                    <span className="mt-1 block text-2xs leading-relaxed text-paper-muted">{lesson.summary}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-3xs text-paper-faint">
                    <Clock className="h-3 w-3" aria-hidden />
                    {lesson.minutes} min
                    <ChevronDown
                      className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")}
                      aria-hidden
                    />
                  </span>
                </button>
                {open ? (
                  <div className="space-y-2.5 border-t border-line-soft px-4 py-3.5 text-2xs leading-relaxed text-paper-muted">
                    {lesson.body.map((paragraph) => (
                      <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </section>

        <aside className="space-y-4">
          <section className="tile p-5" aria-label="Risk disclosure">
            <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
              <AlertTriangle className="h-4 w-4 text-warn" aria-hidden />
              Risk disclosure
            </h2>
            <ul className="mt-3 space-y-2 text-2xs leading-relaxed text-paper-muted">
              <li>Trading leveraged products can lose money rapidly. You can lose more than you deposit with some venues.</li>
              <li>Past performance, simulated or real, does not indicate future results.</li>
              <li>VELTRANE does not manage money, hold funds or guarantee any outcome.</li>
              <li>Automation executes a rule set; it does not remove market risk.</li>
            </ul>
            <Badge tone="warn" className="mt-4">
              Capital at risk
            </Badge>
          </section>

          <section className="tile p-5" aria-label="Costs checklist">
            <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
              <Calculator className="h-4 w-4 text-gold-300" aria-hidden />
              Check before you automate
            </h2>
            <ol className="mt-3 space-y-2 text-2xs leading-relaxed text-paper-muted">
              <li>1. Read the cost line on ten of your own simulated trades.</li>
              <li>2. Set a daily loss limit you would accept on a bad day.</li>
              <li>3. Run the strategy on a demo account for at least a week.</li>
              <li>4. Confirm which mode is live: session or background.</li>
              <li>5. Know where the kill switch is before you need it.</li>
            </ol>
          </section>

          <section className="tile p-5" aria-label="Protections">
            <h2 className="flex items-center gap-2 text-sm font-medium text-paper">
              <ShieldCheck className="h-4 w-4 text-gain" aria-hidden />
              Always on
            </h2>
            <ul className="mt-3 space-y-2 text-2xs leading-relaxed text-paper-muted">
              <li>Independent risk engine on every order.</li>
              <li>Duplicate-order and stale-data rejection.</li>
              <li>Immutable trade detail for every fill.</li>
              <li>Audit log for kills, releases and rejected orders.</li>
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}
