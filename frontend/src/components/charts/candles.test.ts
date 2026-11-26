import { describe, expect, it } from "vitest";
import { CHART_DOWN, CHART_UP, ema, priceScale, rsi, vwap } from "./candles";

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

describe("vwap", () => {
  it("weights each bar by volume, so heavy volume pulls the line closer", () => {
    const out = vwap([
      { ts: 1, open: 100, high: 100, low: 100, close: 100, volume: 1 },
      { ts: 2, open: 200, high: 200, low: 200, close: 200, volume: 9 },
    ]);
    expect(out).toHaveLength(2);
    expect(out[0]).toBe(100);
    // 1 part 100 plus 9 parts 200 = 190
    expect(out[1]).toBeCloseTo(190, 6);
  });

  it("falls back to the typical price when a bar carries no volume", () => {
    const out = vwap([{ ts: 1, open: 10, high: 12, low: 8, close: 10 }]);
    expect(out[0]).toBeCloseTo(10, 6);
  });
});

describe("rsi", () => {
  const closes = [44, 44.3, 44.1, 43.6, 44.3, 44.8, 45.1, 45.5, 45.9, 46.2, 46.1, 46.6, 47, 47.3, 47.5, 47.9];

  it("returns nulls for the warm-up window and one value per bar after it", () => {
    const out = rsi(closes, 14);
    expect(out).toHaveLength(closes.length);
    expect(out.slice(0, 14).every((value) => value === null)).toBe(true);
    expect(out[14]).not.toBeNull();
  });

  it("saturates at 100 when every bar closes higher", () => {
    const rising = Array.from({ length: 20 }, (_, index) => 100 + index);
    expect(rsi(rising, 14).at(-1)).toBe(100);
  });

  it("sits in the middle on a flat series and stays inside 0-100 otherwise", () => {
    const flat = new Array(20).fill(50);
    expect(rsi(flat, 14).at(-1)).toBe(50);
    for (const value of rsi(closes, 14)) {
      if (value !== null) {
        expect(value).toBeGreaterThanOrEqual(0);
        expect(value).toBeLessThanOrEqual(100);
      }
    }
  });

  it("returns only nulls when there is not enough history", () => {
    expect(rsi([1, 2, 3], 14)).toEqual([null, null, null]);
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
