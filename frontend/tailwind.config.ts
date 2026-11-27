import type { Config } from "tailwindcss";

/**
 * VELTRANE design tokens — "Obsidian Instrument".
 *
 * Obsidian and graphite surfaces, electric blue as the action colour, emerald as
 * the value colour. Legacy keys (ink/paper/champagne) are kept as aliases so older
 * screens inherit the new identity instead of drifting out of it.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Every themeable colour resolves from a CSS custom property holding an "r g b"
        // triple, so an administrator can repaint the platform at runtime and Tailwind's
        // alpha modifiers (bg-primary/15) keep working.
        obsidian: {
          950: "rgb(var(--vt-bg) / <alpha-value>)",
          900: "rgb(var(--vt-bg-elev) / <alpha-value>)",
          850: "rgb(var(--vt-bg-850) / <alpha-value>)",
          800: "rgb(var(--vt-bg-800) / <alpha-value>)",
          750: "rgb(var(--vt-bg-750) / <alpha-value>)",
          700: "rgb(var(--vt-bg-700) / <alpha-value>)",
          600: "rgb(var(--vt-bg-600) / <alpha-value>)",
        },
        ink: {
          950: "rgb(var(--vt-bg) / <alpha-value>)",
          900: "rgb(var(--vt-bg-elev) / <alpha-value>)",
          850: "rgb(var(--vt-bg-850) / <alpha-value>)",
          800: "rgb(var(--vt-bg-800) / <alpha-value>)",
          750: "rgb(var(--vt-bg-750) / <alpha-value>)",
          700: "rgb(var(--vt-bg-700) / <alpha-value>)",
          600: "rgb(var(--vt-bg-600) / <alpha-value>)",
        },
        graphite: {
          400: "rgb(var(--vt-text-faint) / <alpha-value>)",
          500: "rgb(var(--vt-text-faint) / <alpha-value>)",
          600: "rgb(var(--vt-line-strong) / <alpha-value>)",
        },
        line: {
          DEFAULT: "rgb(var(--vt-line) / <alpha-value>)",
          soft: "rgb(var(--vt-line-soft) / <alpha-value>)",
          strong: "rgb(var(--vt-line-strong) / <alpha-value>)",
        },
        paper: {
          DEFAULT: "rgb(var(--vt-text) / <alpha-value>)",
          muted: "rgb(var(--vt-text-muted) / <alpha-value>)",
          faint: "rgb(var(--vt-text-faint) / <alpha-value>)",
        },
        electric: {
          100: "rgb(var(--vt-primary-100) / <alpha-value>)",
          200: "rgb(var(--vt-primary-200) / <alpha-value>)",
          300: "rgb(var(--vt-primary-300) / <alpha-value>)",
          400: "rgb(var(--vt-primary-400) / <alpha-value>)",
          500: "rgb(var(--vt-primary-500) / <alpha-value>)",
          600: "rgb(var(--vt-primary-600) / <alpha-value>)",
          700: "rgb(var(--vt-primary-700) / <alpha-value>)",
          900: "rgb(var(--vt-primary-900) / <alpha-value>)",
        },
        // Legacy accent names now follow the secondary accent.
        champagne: {
          200: "rgb(var(--vt-secondary-200) / <alpha-value>)",
          300: "rgb(var(--vt-secondary-300) / <alpha-value>)",
          400: "rgb(var(--vt-secondary-400) / <alpha-value>)",
          500: "rgb(var(--vt-secondary-500) / <alpha-value>)",
          600: "rgb(var(--vt-secondary-600) / <alpha-value>)",
          700: "rgb(var(--vt-secondary-600) / <alpha-value>)",
        },
        gold: {
          300: "rgb(var(--vt-accent-300) / <alpha-value>)",
          400: "rgb(var(--vt-accent-400) / <alpha-value>)",
          500: "rgb(var(--vt-accent-500) / <alpha-value>)",
        },
        platinum: "rgb(var(--vt-text-muted) / <alpha-value>)",
        gain: "rgb(var(--vt-gain) / <alpha-value>)",
        bull: "rgb(var(--vt-gain) / <alpha-value>)",
        loss: "rgb(var(--vt-loss) / <alpha-value>)",
        bear: "rgb(var(--vt-loss) / <alpha-value>)",
        warn: "rgb(var(--vt-warn) / <alpha-value>)",
        info: "rgb(var(--vt-info) / <alpha-value>)",
        chart: {
          up: "rgb(var(--vt-chart-up) / <alpha-value>)",
          down: "rgb(var(--vt-chart-down) / <alpha-value>)",
          grid: "rgb(var(--vt-chart-grid) / <alpha-value>)",
          line: "rgb(var(--vt-chart-line-500) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "rgb(var(--vt-primary-500) / <alpha-value>)",
          hover: "rgb(var(--vt-primary-600) / <alpha-value>)",
          foreground: "rgb(var(--vt-button-text) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "Inter",
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        display: [
          "var(--font-display)",
          "Space Grotesk",
          "Inter",
          "ui-sans-serif",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1.05rem" }],
        "3xs": ["0.625rem", { lineHeight: "0.9rem" }],
      },
      letterSpacing: {
        label: "0.13em",
        wordmark: "0.34em",
      },
      transitionTimingFunction: {
        smooth: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      borderRadius: {
        lg: "0.625rem",
        xl: "0.875rem",
        "2xl": "1.125rem",
        "3xl": "1.5rem",
        control: "var(--radius-control)",
        card: "var(--radius-card)",
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.035) inset, 0 30px 70px -46px rgba(0,0,0,0.85)",
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 18px 40px -30px rgba(0,0,0,0.8)",
        lift: "0 24px 60px -32px rgba(0,0,0,0.9)",
        glow: "0 0 0 1px rgba(203,182,145,0.32), 0 18px 50px -22px rgba(203,182,145,0.45)",
        "glow-emerald": "0 0 0 1px rgba(16,185,129,0.35), 0 18px 50px -24px rgba(16,185,129,0.45)",
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(circle at 18% 0%, rgba(203,182,145,0.10), transparent 46%), radial-gradient(circle at 86% 8%, rgba(22,199,132,0.07), transparent 42%)",
        aurora:
          "radial-gradient(60% 55% at 50% 0%, rgba(203,182,145,0.14), transparent 70%), radial-gradient(45% 40% at 85% 20%, rgba(92,155,255,0.10), transparent 70%)",
        sheen: "linear-gradient(115deg, transparent 20%, rgba(255,255,255,0.06) 45%, transparent 65%)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        ticker: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
        pulseRing: {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(1.6)", opacity: "0" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        scan: { from: { transform: "translateY(-100%)" }, to: { transform: "translateY(100%)" } },
      },
      animation: {
        "fade-up": "fade-up 0.45s cubic-bezier(0.16,1,0.3,1) both",
        "fade-in": "fade-in 0.4s ease-out both",
        shimmer: "shimmer 1.8s infinite",
        ticker: "ticker 42s linear infinite",
        float: "float 7s ease-in-out infinite",
        "pulse-ring": "pulseRing 2.4s ease-out infinite",
        scan: "scan 6s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
