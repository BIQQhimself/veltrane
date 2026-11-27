import Link from "next/link";
import { Wordmark } from "@/components/brand";

const NAV = [
  ["Terminal", "/app/terminal"],
  ["Markets", "/app/markets"],
  ["Strategies", "/app/strategies"],
  ["Risk policy", "/risk"],
  ["Security", "/security"],
] as const;

export function DocShell({
  eyebrow,
  title,
  summary,
  version,
  children,
}: {
  eyebrow: string;
  title: string;
  summary: string;
  version: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-obsidian-950 text-paper">
      <header className="sticky top-0 z-40 border-b border-line-soft bg-obsidian-950/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-5 lg:px-8">
          <Link href="/" aria-label="VELTRANE home">
            <Wordmark />
          </Link>
          <nav className="hidden items-center gap-7 md:flex" aria-label="Primary">
            {NAV.map(([label, href]) => (
              <Link
                key={href}
                href={href}
                className="text-xs text-paper-muted transition-colors hover:text-paper"
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="rounded-lg px-3 py-2 text-xs text-paper-muted transition-colors hover:text-paper"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              className="cta-gold inline-flex items-center rounded-lg px-3.5 py-2 text-xs font-medium transition"
            >
              Create account
            </Link>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-3xl px-5 py-16 lg:px-8 lg:py-24">
        <p className="text-2xs uppercase tracking-label text-champagne-300">{eyebrow}</p>
        <h1 className="mt-4 font-display text-4xl tracking-tight text-paper lg:text-5xl">{title}</h1>
        <p className="mt-5 max-w-2xl text-sm leading-relaxed text-paper-muted">{summary}</p>
        <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-line-soft px-3 py-1 text-2xs text-paper-faint">
          Document version <span className="text-paper-muted">{version}</span>
        </p>
        <div className="mt-12 space-y-12 border-t border-line-soft pt-12">{children}</div>
      </main>

      <footer className="border-t border-line-soft">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-10 text-2xs text-paper-faint lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <p className="max-w-xl leading-relaxed">
            VELTRANE is a trading technology provider. It does not hold client funds, does not
            manage portfolios, and does not guarantee outcomes.
          </p>
          <div className="flex gap-5">
            <Link href="/risk" className="transition hover:text-paper">
              Risk policy
            </Link>
            <Link href="/security" className="transition hover:text-paper">
              Security
            </Link>
            <Link href="/" className="transition hover:text-paper">
              Home
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function DocSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="font-display text-xl tracking-tight text-paper">{title}</h2>
      <div className="mt-4 space-y-4 text-sm leading-relaxed text-paper-muted">{children}</div>
    </section>
  );
}

export function DocList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="space-y-2.5">
      {items.map((item, index) => (
        <li key={index} className="flex gap-3">
          <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-champagne-400" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function DocTable({
  head,
  rows,
}: {
  head: string[];
  rows: string[][];
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line-soft">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-line-soft bg-white/[0.02]">
            {head.map((cell) => (
              <th
                key={cell}
                scope="col"
                className="px-4 py-3 text-2xs font-medium uppercase tracking-label text-paper-faint"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[0]} className="border-b border-line-soft/60 last:border-0">
              {row.map((cell, index) => (
                <td
                  key={index}
                  className={
                    index === 0
                      ? "px-4 py-3 font-mono text-2xs text-paper"
                      : "px-4 py-3 text-paper-muted"
                  }
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
