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
        obsidian: {
          950: "#04060a",
          900: "#070a10",
          850: "#0a0e15",
          800: "#0e131b",
          750: "#121821",
          700: "#18202b",
          600: "#212b38",
        },
        ink: {
          950: "#04060a",
          900: "#070a10",
          850: "#0a0e15",
          800: "#0e131b",
          750: "#121821",
          700: "#18202b",
          600: "#212b38",
        },
        graphite: {
          400: "#4a5768",
          500: "#38434f",
          600: "#2a3440",
        },
        line: {
          DEFAULT: "#1b2430",
          soft: "#141a23",
          strong: "#2b3846",
        },
        paper: {
          DEFAULT: "#e8edf4",
          muted: "#98a6b8",
          faint: "#6a788b",
        },
        electric: {
          200: "#c7ddff",
          300: "#8fbbff",
          400: "#5c9bff",
          500: "#2e7bff",
          600: "#1b5fe0",
          700: "#1647a8",
          900: "#0c2450",
        },
        emerald: {
          200: "#b8f5dc",
          300: "#6ee7b7",
          400: "#34d399",
          500: "#10b981",
          600: "#059669",
          700: "#047857",
          900: "#04352a",
        },
        // Legacy accent names resolve to the new palette.
        champagne: {
          300: "#8fbbff",
          400: "#5c9bff",
          500: "#2e7bff",
          600: "#1b5fe0",
          700: "#1647a8",
        },
        gold: {
          300: "#f0dcb4",
          400: "#dcc08a",
          500: "#c3a068",
        },
        platinum: "#c6cedb",
        gain: "#10b981",
        loss: "#f2555f",
        warn: "#f0b429",
        info: "#5c9bff",
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
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        "3xs": ["0.625rem", { lineHeight: "0.875rem" }],
      },
      letterSpacing: {
        label: "0.14em",
        wordmark: "0.34em",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 28px 70px -40px rgba(0,0,0,0.95)",
        lift: "0 24px 60px -32px rgba(0,0,0,0.9)",
        glow: "0 0 0 1px rgba(46,123,255,0.35), 0 18px 50px -22px rgba(46,123,255,0.55)",
        "glow-emerald": "0 0 0 1px rgba(16,185,129,0.35), 0 18px 50px -24px rgba(16,185,129,0.45)",
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(circle at 18% 0%, rgba(46,123,255,0.14), transparent 46%), radial-gradient(circle at 86% 8%, rgba(16,185,129,0.10), transparent 42%)",
        aurora:
          "radial-gradient(60% 55% at 50% 0%, rgba(46,123,255,0.20), transparent 70%), radial-gradient(45% 40% at 85% 20%, rgba(16,185,129,0.14), transparent 70%)",
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
