import { describe, expect, it } from "vitest";
import { CHART_DOWN, CHART_UP, ema, priceScale } from "./candles";

const ethCandles = [
  { high: 3312, low: 3122 },
  { high: 3200, low: 3150 },
];

describe("priceScale", () => {
  it("brackets the candle range with padding", () => {
    const scale = priceScale(ethCandles);
    expect(scale.min).toBe(3122);
    expect(scale.max).toBe(3312);
    expect(scale.lo).toBeLessThan(scale.min);
    expect(scale.hi).toBeGreaterThan(scale.max);
  });

  it("includes a live price that sits inside the candle range", () => {
    const scale = priceScale(ethCandles, [3178]);
    expect(scale.lo).toBeLessThanOrEqual(3178);
    expect(scale.hi).toBeGreaterThanOrEqual(3178);
  });

  it("ignores a marker from another instrument", () => {
    const withBtcQuote = priceScale(ethCandles, [64368]);
    expect(withBtcQuote).toEqual(priceScale(ethCandles));
    expect(withBtcQuote.hi).toBeLessThan(10000);
  });

  it("ignores null, undefined and non-finite markers", () => {
    const scale = priceScale(ethCandles, [null, undefined, Number.NaN, 0, -5]);
    expect(scale).toEqual(priceScale(ethCandles));
  });

  it("falls back to the marker when no candles are loaded", () => {
    const scale = priceScale([], [3178]);
    expect(scale.min).toBe(3178);
    expect(scale.max).toBe(3178);
    expect(scale.hi).toBeGreaterThan(scale.lo);
  });

  it("never returns a zero-width scale", () => {
    const scale = priceScale([{ high: 100, low: 100 }]);
    expect(scale.hi).toBeGreaterThan(scale.lo);
  });
});

describe("ema", () => {
  it("returns one value per input and seeds on the first close", () => {
    const out = ema([10, 11, 12, 13], 3);
    expect(out).toHaveLength(4);
    expect(out[0]).toBe(10);
    expect(out[3]).toBeGreaterThan(out[2]!);
  });

  it("smooths a spike instead of following it exactly", () => {
    const out = ema([100, 100, 100, 200, 100], 5);
    expect(out[3]).toBeLessThan(200);
    expect(out[3]).toBeGreaterThan(100);
  });

  it("handles empty input and degenerate periods", () => {
    expect(ema([], 14)).toEqual([]);
    expect(ema([5, 6], 0)).toEqual([]);
  });
});

describe("chart palette", () => {
  it("keeps bull and bear colours vivid and distinct", () => {
    const luminance = (hex: string) => {
      const channel = (offset: number) => parseInt(hex.slice(offset, offset + 2), 16) / 255;
      return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
    };
    expect(CHART_UP).not.toBe(CHART_DOWN);
    // Saturated green must stay clearly brighter than the dark red, so a candle's
    // direction reads without relying on colour alone (shape + luminance both differ).
    expect(luminance(CHART_UP)).toBeGreaterThan(luminance(CHART_DOWN) + 0.2);
  });
});
