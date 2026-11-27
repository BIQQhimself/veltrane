import Link from "next/link";
import { ArrowLeft, Lock, ShieldCheck, Timer } from "lucide-react";
import { Wordmark } from "@/components/brand";

const POINTS = [
  {
    icon: ShieldCheck,
    title: "An independent risk engine",
    body: "Size, exposure, drawdown and duplicate orders are checked before any contract opens. The strategy layer cannot bypass it.",
  },
  {
    icon: Lock,
    title: "Your accounts, your keys",
    body: "VELTRANE never holds funds. Connections are trading-only, encrypted at rest, and read-only until you authorise otherwise.",
  },
  {
    icon: Timer,
    title: "Simulation first, always",
    body: "Every new account starts in paper mode. Live execution needs a completed checklist and an explicit, separate opt-in.",
  },
];

/**
 * The signed-out frame: brand and the non-negotiables on the left, the form on the right.
 * It keeps the marketing promise next to the moment a person hands over their email.
 */
export function AuthShell({
  eyebrow,
  title,
  description,
  children,
  footer,
  width = "md",
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
  footer: React.ReactNode;
  width?: "sm" | "md";
}) {
  return (
    <main id="main" className="relative min-h-screen">
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-60" aria-hidden />
      <div className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col px-5 py-8 sm:px-8">
        <header className="flex items-center justify-between">
          <Link href="/" aria-label="VELTRANE home">
            <Wordmark />
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-full border border-line-soft px-3 py-1.5 text-2xs text-paper-muted transition hover:border-line-strong hover:text-paper"
          >
            <ArrowLeft className="h-3 w-3" aria-hidden />
            Back to site
          </Link>
        </header>

        <div className="grid flex-1 items-center gap-14 py-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)] lg:gap-20">
          <section className="hidden lg:block">
            <p className="label">{eyebrow}</p>
            <h2 className="mt-3 max-w-md font-display text-[34px] font-medium leading-[1.12] tracking-tight text-paper">
              Precision trading, with the brakes wired in.
            </h2>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-paper-muted">
              Fixed-odds contracts and CFD-style execution in one terminal, priced in the open, with a
              copilot that shows its reasoning instead of promising an outcome.
            </p>
            <ul className="mt-8 space-y-5">
              {POINTS.map((point) => (
                <li key={point.title} className="flex gap-3.5">
                  <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line-soft bg-obsidian-700/50 text-champagne-600">
                    <point.icon className="h-4 w-4" aria-hidden />
                  </span>
                  <div>
                    <p className="text-[13px] font-medium text-paper">{point.title}</p>
                    <p className="mt-0.5 max-w-sm text-xs leading-relaxed text-paper-faint">{point.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section
            className={
              width === "sm"
                ? "w-full max-w-sm justify-self-center lg:justify-self-end"
                : "w-full justify-self-center lg:justify-self-end"
            }
          >
            <div className="tile tile-sheen p-6 sm:p-7">
              <h1 className="font-display text-[26px] font-medium leading-tight tracking-tight text-paper">{title}</h1>
              <p className="mt-2 text-[13px] leading-relaxed text-paper-muted">{description}</p>
              <div className="mt-6">{children}</div>
            </div>
            <div className="mt-5 text-center text-xs text-paper-faint">{footer}</div>
          </section>
        </div>

        <footer className="border-t border-line-soft pt-4 text-3xs leading-relaxed text-paper-faint">
          Simulated results are not predictions of future returns. Fixed-odds contracts are high risk and
          most short-dated positions lose money after costs.
        </footer>
      </div>
    </main>
  );
}
