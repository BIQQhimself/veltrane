import { describe, expect, it } from "vitest";
import {
  applyVars,
  contrastRatio,
  DEFAULT_COLORS,
  deriveVars,
  hexToRgb,
  isLightColor,
  normalize,
  shade,
} from "./theme";

/** "12 34 56" -> channel sum, for ordering shades without repeating arithmetic. */
function sum(triple: string | undefined): number {
  return (triple ?? "0 0 0").split(" ").map(Number).reduce((a, b) => a + b, 0);
}

function tripleOf(hex: string | undefined): string {
  const rgb = hexToRgb(hex ?? "#000000");
  return rgb ? `${rgb.r} ${rgb.g} ${rgb.b}` : "0 0 0";
}

function hexOf(triple: string | undefined): string {
  const channels = (triple ?? "0 0 0").split(" ").map(Number);
  return `#${channels.map((n) => (n ?? 0).toString(16).padStart(2, "0")).join("")}`;
}

describe("theme derivation", () => {
  it("parses six-digit hex and rejects anything else", () => {
    expect(hexToRgb("#2e7bff")).toEqual({ r: 46, g: 123, b: 255 });
    expect(hexToRgb("2e7bff")).toEqual({ r: 46, g: 123, b: 255 });
    for (const bad of ["red", "#12345", "#1234567", "", "url(javascript:1)"]) {
      expect(hexToRgb(bad)).toBeNull();
    }
  });

  it("mixes toward white and black", () => {
    expect(shade("#000000", 1)).toBe("#ffffff");
    expect(shade("#ffffff", -1)).toBe("#000000");
    expect(shade("#808080", 0)).toBe("#808080");
  });

  it("emits every variable Tailwind reads, as an r g b triple", () => {
    const vars = deriveVars(DEFAULT_COLORS);
    for (const name of [
      "vt-bg",
      "vt-line",
      "vt-text",
      "vt-primary-500",
      "vt-chart-up",
      "vt-gain",
      "vt-contrast",
      "vt-contrast-raised",
      "vt-contrast-text",
      "vt-contrast-muted",
    ]) {
      expect(vars[name]).toMatch(/^\d{1,3} \d{1,3} \d{1,3}$/);
    }
    // The base stop is the administrator's colour, untouched.
    expect(vars["vt-primary-500"]).toBe(tripleOf(DEFAULT_COLORS.primary));
  });

  it("re-derives the whole scale from a changed base colour", () => {
    const vars = deriveVars({ ...DEFAULT_COLORS, primary: "#123456" });
    expect(vars["vt-primary-500"]).toBe("18 52 86");
    // Lighter stops are lighter, darker stops are darker.
    const stop = (n: number) => (vars[`vt-primary-${n}`] ?? "0 0 0").split(" ").map(Number);
    const sum = (n: number) => stop(n).reduce((a, b) => a + b, 0);
    expect(sum(300)).toBeGreaterThan(sum(500));
    expect(sum(700)).toBeLessThan(sum(500));
  });

  it("applies variables through setProperty so alpha utilities keep working", () => {
    const written: Record<string, string> = {};
    applyVars({ style: { setProperty: (k, v) => void (written[k] = v) } }, { "vt-bg": "1 2 3" });
    expect(written["--vt-bg"]).toBe("1 2 3");
  });

  it("normalises a partial payload onto the defaults", () => {
    const theme = normalize({ colors: { primary: "#abcdef" } });
    expect(theme.colors.primary).toBe("#abcdef");
    expect(theme.colors.background).toBe(DEFAULT_COLORS.background);
    expect(theme.branding.product_name).toBe("VELTRANE");
  });

  it("survives a payload with no colours at all", () => {
    expect(() => deriveVars({})).not.toThrow();
    expect(normalize(null).colors).toEqual(DEFAULT_COLORS);
  });

  it("derives raised surfaces in the direction the palette needs", () => {
    // Dark chrome: raised surfaces are lighter than the base, hairlines darker.
    const dark = deriveVars({
      ...DEFAULT_COLORS,
      background: "#04060a",
      surface: "#0a0e15",
      surface_raised: "#121821",
      border: "#1b2430",
      text: "#e8edf4",
      text_muted: "#98a6b8",
    });
    expect(sum(dark["vt-bg-700"])).toBeGreaterThan(sum(dark["vt-bg-800"]));
    expect(sum(dark["vt-line-soft"])).toBeLessThan(sum(dark["vt-line"]));

    // Light chrome: the same roles invert, or hover states vanish into white.
    const light = deriveVars(DEFAULT_COLORS);
    expect(sum(light["vt-bg-700"])).toBeLessThan(sum(light["vt-bg-800"]));
    expect(sum(light["vt-line-soft"])).toBeGreaterThan(sum(light["vt-line"]));
    expect(sum(light["vt-text-faint"])).toBeGreaterThan(sum(light["vt-text-muted"]));
  });

  it("keeps the instrument surface dark whatever the chrome does", () => {
    const light = deriveVars(DEFAULT_COLORS);
    expect(sum(light["vt-contrast"])).toBeLessThan(200);
    expect(sum(light["vt-contrast-raised"])).toBeGreaterThan(sum(light["vt-contrast"]));
    expect(contrastRatio(hexOf(light["vt-contrast"]), hexOf(light["vt-contrast-text"]))).toBeGreaterThan(7);
  });

  it("classifies light and dark chrome", () => {
    expect(isLightColor("#eef1f7")).toBe(true);
    expect(isLightColor("#ffffff")).toBe(true);
    expect(isLightColor("#04060a")).toBe(false);
    expect(isLightColor("#0f1a2e")).toBe(false);
    expect(isLightColor("not-a-colour")).toBe(false);
  });

  it("keeps every shipped text pairing at WCAG AA or better", () => {
    // The redesign moved the platform from dark chrome to light chrome. These assertions are
    // the guard against the failure that motivates them: a palette edit that leaves
    // secondary text, a profit figure or a button label below 4.5:1 on its own surface.
    const c = DEFAULT_COLORS;
    const pairs: Array<[string, string | undefined, string | undefined]> = [
      ["body text on the app background", c.text, c.background],
      ["body text on a card", c.text, c.surface],
      ["secondary text on the app background", c.text_muted, c.background],
      ["secondary text on a card", c.text_muted, c.surface],
      ["primary button label", c.button_text, c.primary],
      ["label on a gold fill", c.on_accent, c.accent],
      ["profit figure on a card", c.gain, c.surface],
      ["loss figure on a card", c.loss, c.surface],
      ["warning text on a card", c.warn, c.surface],
      ["secondary accent text on a card", c.secondary, c.surface],
      ["chart labels on the instrument surface", c.contrast_text, c.contrast_surface],
    ];
    for (const [name, fg, bg] of pairs) {
      expect(contrastRatio(fg ?? "#000000", bg ?? "#ffffff"), name).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keeps derived faint and gold text readable", () => {
    const vars = deriveVars(DEFAULT_COLORS);
    // `faint` is the caption colour and `gold-600` the premium label colour; both are derived
    // rather than chosen, so they need their own check.
    expect(contrastRatio(hexOf(vars["vt-text-faint"]), DEFAULT_COLORS.surface ?? "#fff")).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(hexOf(vars["vt-accent-600"]), DEFAULT_COLORS.surface ?? "#fff")).toBeGreaterThanOrEqual(4.5);
  });

  it("measures contrast for the accessibility hint", () => {
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 0);
    expect(contrastRatio("#777777", "#777777")).toBeCloseTo(1, 5);
    // The shipped text/background pairing must stay readable.
    expect(contrastRatio(DEFAULT_COLORS.text ?? "#fff", DEFAULT_COLORS.background ?? "#000")).toBeGreaterThan(4.5);
  });
});
