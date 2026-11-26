import { describe, expect, it } from "vitest";
import { priceScale } from "./candles";

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
