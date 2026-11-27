/**
 * Runtime visual identity.
 *
 * The API stores a small palette (18 base colours). This module turns it into the full set of
 * CSS custom properties the Tailwind theme reads, so an administrator can restyle the platform
 * without a rebuild. Shades are derived by mixing toward white or black, which keeps every
 * `bg-electric-500/15`-style utility in the codebase working: each variable holds an
 * `r g b` triple, so Tailwind can still apply an alpha channel.
 */

export type ThemeColors = Record<string, string>;

export type ThemeBranding = {
  product_name: string;
  logo_mark: string;
  default_theme: string;
  tagline: string;
};

export type ThemePayload = {
  colors: ThemeColors;
  branding: ThemeBranding;
  source?: string;
  updated_at?: string | null;
  updated_by?: string | null;
};

export const DEFAULT_COLORS: ThemeColors = {
  background: "#04060a",
  surface: "#0a0e15",
  surface_raised: "#121821",
  border: "#1b2430",
  text: "#e8edf4",
  text_muted: "#98a6b8",
  primary: "#2e7bff",
  primary_hover: "#1b5fe0",
  secondary: "#d6c39a",
  accent: "#dcc08a",
  button_text: "#ffffff",
  chart_up: "#00e07a",
  chart_down: "#ff3b52",
  chart_grid: "#141a23",
  chart_line: "#5c9bff",
  gain: "#00e07a",
  loss: "#ff3b52",
  warn: "#f0b429",
};

export const DEFAULT_BRANDING: ThemeBranding = {
  product_name: "VELTRANE",
  logo_mark: "V",
  default_theme: "obsidian",
  tagline: "Autonomous trading, under your control",
};

export const DEFAULT_THEME: ThemePayload = {
  colors: DEFAULT_COLORS,
  branding: DEFAULT_BRANDING,
  source: "default",
};

type Rgb = { r: number; g: number; b: number };

export function hexToRgb(hex: string): Rgb | null {
  const match = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!match) return null;
  const value = parseInt(match[1] ?? "000000", 16);
  return { r: (value >> 16) & 255, g: (value >> 8) & 255, b: value & 255 };
}

export function rgbToHex({ r, g, b }: Rgb): string {
  const part = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

/** Mix a colour toward white (amount > 0) or black (amount < 0). */
export function shade(hex: string, amount: number): string {
  const rgb = hexToRgb(hex) ?? { r: 0, g: 0, b: 0 };
  const target = amount >= 0 ? 255 : 0;
  const ratio = Math.abs(amount);
  return rgbToHex({
    r: rgb.r + (target - rgb.r) * ratio,
    g: rgb.g + (target - rgb.g) * ratio,
    b: rgb.b + (target - rgb.b) * ratio,
  });
}

function triple(hex: string): string {
  const rgb = hexToRgb(hex) ?? { r: 0, g: 0, b: 0 };
  return `${rgb.r} ${rgb.g} ${rgb.b}`;
}

/**
 * The variables Tailwind reads. Keys are CSS custom properties without the `--` prefix.
 * A scale is generated per role so existing utility classes (electric-200 … electric-900)
 * keep their relative lightness whatever base colour the administrator picks.
 */
export function deriveVars(colors: ThemeColors): Record<string, string> {
  const c: Record<string, string> = { ...DEFAULT_COLORS, ...colors };
  const pick = (key: string): string => c[key] ?? DEFAULT_COLORS[key] ?? "#000000";
  const scale = (base: string, stops: number[]) => {
    const out: Record<string, string> = {};
    for (const stop of stops) {
      // 100 is lightest, 900 darkest; 500 is the base colour itself.
      const amount = stop < 500 ? (500 - stop) / 500 : -(stop - 500) / 500;
      out[`vt-${base}-${stop}`] = triple(shade(c[base] ?? "#000000", amount * 0.9));
    }
    out[`vt-${base}-500`] = triple(c[base] ?? "#000000");
    return out;
  };

  return {
    "vt-bg": triple(pick("background")),
    "vt-bg-elev": triple(shade(pick("surface"), 0.02)),
    "vt-bg-850": triple(pick("surface")),
    "vt-bg-800": triple(pick("surface_raised")),
    "vt-bg-750": triple(shade(pick("surface_raised"), 0.04)),
    "vt-bg-700": triple(shade(pick("surface_raised"), 0.09)),
    "vt-bg-600": triple(shade(pick("surface_raised"), 0.16)),
    "vt-line": triple(pick("border")),
    "vt-line-soft": triple(shade(pick("border"), -0.25)),
    "vt-line-strong": triple(shade(pick("border"), 0.16)),
    "vt-text": triple(pick("text")),
    "vt-text-muted": triple(pick("text_muted")),
    "vt-text-faint": triple(shade(pick("text_muted"), -0.28)),
    "vt-button-text": triple(pick("button_text")),
    "vt-chart-grid": triple(pick("chart_grid")),
    ...scale("primary", [100, 200, 300, 400, 500, 600, 700, 900]),
    ...scale("secondary", [200, 300, 400, 500, 600]),
    ...scale("accent", [300, 400, 500]),
    ...scale("chart-line", [400, 500]),
    "vt-chart-up": triple(pick("chart_up")),
    "vt-chart-down": triple(pick("chart_down")),
    "vt-gain": triple(pick("gain")),
    "vt-loss": triple(pick("loss")),
    "vt-warn": triple(pick("warn")),
    "vt-info": triple(pick("chart_line")),
  };
}

/** Apply a payload to a document element. Kept separate from React so tests can call it. */
export function applyVars(
  root: { style: { setProperty: (name: string, value: string) => void } },
  vars: Record<string, string>,
): void {
  for (const [name, value] of Object.entries(vars)) {
    root.style.setProperty(`--${name}`, value);
  }
}

export function normalize(payload: Partial<ThemePayload> | null | undefined): ThemePayload {
  return {
    colors: { ...DEFAULT_COLORS, ...(payload?.colors ?? {}) },
    branding: { ...DEFAULT_BRANDING, ...(payload?.branding ?? {}) },
    source: payload?.source ?? "default",
    updated_at: payload?.updated_at ?? null,
    updated_by: payload?.updated_by ?? null,
  };
}

/** Contraste ratio per WCAG 2.1, used by the admin form to warn about unreadable pairings. */
export function contrastRatio(a: string, b: string): number {
  const lum = (hex: string) => {
    const rgb = hexToRgb(hex);
    if (!rgb) return 0;
    const channel = (v: number) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
  };
  const sorted = [lum(a), lum(b)].sort((x, y) => y - x);
  const light = sorted[0] ?? 1;
  const dark = sorted[1] ?? 0;
  return (light + 0.05) / (dark + 0.05);
}
