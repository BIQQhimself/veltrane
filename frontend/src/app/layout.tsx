import type { Metadata, Viewport } from "next";
import { ToastProvider } from "@/components/ui/toast";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "VELTRANE — Autonomous trading with institutional discipline",
    template: "%s · VELTRANE",
  },
  description:
    "VELTRANE is a multi-tenant trading workspace: connect your own exchange or broker read-only, run deterministic strategies in simulation, and enable live trading only after explicit, multi-step authorisation. VELTRANE never holds your funds.",
  applicationName: "VELTRANE",
  robots: { index: true, follow: true },
  openGraph: {
    title: "VELTRANE",
    description: "Autonomous trading with institutional discipline. Your capital stays with your broker.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#05070d",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-ink-950 font-sans antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-champagne-500 focus:px-3 focus:py-2 focus:text-sm focus:text-ink-950"
        >
          Skip to content
        </a>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
