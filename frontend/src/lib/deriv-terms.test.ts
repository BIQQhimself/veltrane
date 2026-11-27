import { describe, expect, it } from "vitest";
import { groupTerms, parseTerm, venueTermOptions } from "./deriv";

describe("parseTerm", () => {
  it("reads the units Deriv publishes", () => {
    expect(parseTerm("30s")).toEqual({ term: "30s", value: 30, unit: "s", label: "30 sec" });
    expect(parseTerm("1t")?.label).toBe("1 tick");
    expect(parseTerm("5t")?.label).toBe("5 ticks");
    expect(parseTerm("1d")?.label).toBe("1 day");
  });

  it("refuses anything that is not a venue term", () => {
    expect(parseTerm("")).toBeNull();
    expect(parseTerm("30")).toBeNull();
    expect(parseTerm("30x")).toBeNull();
    expect(parseTerm("s30")).toBeNull();
    expect(parseTerm("1.5h")).toBeNull();
  });
});

describe("venueTermOptions", () => {
  it("returns nothing when the venue has not answered", () => {
    expect(venueTermOptions(undefined)).toEqual([]);
    expect(venueTermOptions({})).toEqual([]);
  });

  it("unions CALL and PUT without duplicating a term", () => {
    const options = venueTermOptions({
      CALL: { terms: ["1t", "5t", "15s", "30s"] },
      PUT: { terms: ["5t", "30s", "60s"] },
    });
    expect(options.map((item) => item.term)).toEqual(["1t", "5t", "15s", "30s", "60s"]);
  });

  it("orders by unit then value, so the menu reads like a ladder", () => {
    const options = venueTermOptions({
      CALL: { terms: ["1d", "30m", "30s", "5t", "1h", "15s"] },
    });
    expect(options.map((item) => item.term)).toEqual(["5t", "15s", "30s", "30m", "1h", "1d"]);
  });

  it("drops entries the venue sent that are not terms", () => {
    const options = venueTermOptions({ CALL: { terms: ["15s", "abc", "", "1y"] } });
    expect(options.map((item) => item.term)).toEqual(["15s"]);
  });

  it("groups the menu by unit for a grouped select", () => {
    const options = venueTermOptions({ CALL: { terms: ["5t", "15s", "30s", "1h"] } });
    const groups = groupTerms(options);
    expect(groups.map((group) => group.label)).toEqual(["ticks", "sec", "hours"]);
    expect(groups[1]?.items.map((item) => item.term)).toEqual(["15s", "30s"]);
  });
});
