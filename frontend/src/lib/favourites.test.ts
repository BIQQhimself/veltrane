import { describe, expect, it } from "vitest";
import { orderFavourites, toggleFavourite } from "./favourites";

describe("favourites", () => {
  it("adds an instrument and removes it again", () => {
    const added = toggleFavourite([], "BTC/USD");
    expect(added).toEqual(["BTC/USD"]);
    expect(toggleFavourite(added, "BTC/USD")).toEqual([]);
  });

  it("keeps the most recent twelve and drops the oldest", () => {
    let list: string[] = [];
    for (let index = 0; index < 14; index += 1) list = toggleFavourite(list, `SYM${index}`);
    expect(list).toHaveLength(12);
    expect(list).not.toContain("SYM0");
    expect(list.at(-1)).toBe("SYM13");
  });

  it("drops instruments the venue no longer offers", () => {
    const stored = ["BTC/USD", "OLD/USD", "ETH/USD"];
    expect(orderFavourites(stored, ["BTC/USD", "ETH/USD"])).toEqual(["BTC/USD", "ETH/USD"]);
  });

  it("returns an empty list when nothing is available yet", () => {
    expect(orderFavourites(["BTC/USD"], [])).toEqual([]);
  });
});
