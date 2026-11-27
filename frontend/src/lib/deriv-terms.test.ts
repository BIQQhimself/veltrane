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
      CALL: { terms: ["60s", "5m"] },
      PUT: { terms: ["5m", "15m"] },
    });
    expect(options.map((item) => item.term)).toEqual(["60s", "5m", "15m"]);
  });

  it("never offers a tick or a sub-minute term, even if the venue sends one", () => {
    const options = venueTermOptions({
      CALL: { terms: ["1t", "5t", "15s", "30s", "45s", "59s", "60s"] },
      PUT: { terms: ["5t", "30s", "90s"] },
    });
    expect(options.map((item) => item.term)).toEqual(["60s", "90s"]);
  });

  it("orders by unit then value, so the menu reads like a ladder", () => {
    const options = venueTermOptions({
      CALL: { terms: ["1d", "30m", "60s", "1h", "5m"] },
    });
    expect(options.map((item) => item.term)).toEqual(["60s", "5m", "30m", "1h", "1d"]);
  });

  it("drops entries the venue sent that are not terms", () => {
    const options = venueTermOptions({ CALL: { terms: ["60s", "abc", "", "1y"] } });
    expect(options.map((item) => item.term)).toEqual(["60s"]);
  });

  it("groups the menu by unit for a grouped select", () => {
    const options = venueTermOptions({ CALL: { terms: ["60s", "5m", "1h"] } });
    const groups = groupTerms(options);
    expect(groups.map((group) => group.label)).toEqual(["sec", "min", "hours"]);
    expect(groups[0]?.items.map((item) => item.term)).toEqual(["60s"]);
  });
});
