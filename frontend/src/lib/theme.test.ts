import { describe, expect, it } from "vitest";
import {
  applyVars,
  contrastRatio,
  DEFAULT_COLORS,
  deriveVars,
  hexToRgb,
  normalize,
  shade,
} from "./theme";

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
    for (const name of ["vt-bg", "vt-line", "vt-text", "vt-primary-500", "vt-chart-up", "vt-gain"]) {
      expect(vars[name]).toMatch(/^\d{1,3} \d{1,3} \d{1,3}$/);
    }
    // The base stop is the administrator's colour, untouched.
    expect(vars["vt-primary-500"]).toBe("203 182 145");
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

  it("measures contrast for the accessibility hint", () => {
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 0);
    expect(contrastRatio("#777777", "#777777")).toBeCloseTo(1, 5);
    // The shipped text/background pairing must stay readable.
    expect(contrastRatio(DEFAULT_COLORS.text ?? "#fff", DEFAULT_COLORS.background ?? "#000")).toBeGreaterThan(4.5);
  });
});
