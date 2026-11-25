import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#05070d",
          900: "#080c15",
          850: "#0a101b",
          800: "#0d1420",
          750: "#111a28",
          700: "#16202f",
          600: "#1e2a3b",
        },
        line: {
          DEFAULT: "#1a2333",
          soft: "#141b27",
          strong: "#26334a",
        },
        paper: {
          DEFAULT: "#e9edf4",
          muted: "#9aa5b8",
          faint: "#6b7689",
        },
        champagne: {
          300: "#e7d3a6",
          400: "#d7bd85",
          500: "#c8a96a",
          600: "#a8894f",
          700: "#7f6739",
        },
        platinum: "#c6cedb",
        gain: "#3fb27f",
        loss: "#e0606f",
        warn: "#d9a441",
        info: "#6a9bd8",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Inter",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        display: ["ui-serif", "Georgia", "Iowan Old Style", "Times New Roman", "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      letterSpacing: {
        label: "0.14em",
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 24px 60px -32px rgba(0,0,0,0.9)",
        lift: "0 18px 40px -24px rgba(0,0,0,0.85)",
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(circle at 20% 0%, rgba(200,169,106,0.10), transparent 45%), radial-gradient(circle at 85% 10%, rgba(106,155,216,0.08), transparent 40%)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
