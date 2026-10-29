import { beforeEach, describe, expect, it } from "vitest";

import {
  getStoredColorRanges,
  resolveMetricColorRange,
  setStoredColorRanges,
} from "../metricColorRanges";

describe("metricColorRanges", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips ranges per chip", () => {
    setStoredColorRanges("chipA", { t1: { min: 10, max: 120 } });
    setStoredColorRanges("chipB", { t1: { min: 0, max: 50 } });
    expect(getStoredColorRanges("chipA")).toEqual({
      t1: { min: 10, max: 120 },
    });
    expect(getStoredColorRanges("chipB")).toEqual({ t1: { min: 0, max: 50 } });
  });

  it("drops invalid entries when reading", () => {
    localStorage.setItem(
      "qdash_metric_color_ranges:chipA",
      JSON.stringify({
        t1: { min: 5, max: 1 },
        t2_echo: { min: 1, max: 2 },
        junk: "x",
      }),
    );
    expect(getStoredColorRanges("chipA")).toEqual({
      t2_echo: { min: 1, max: 2 },
    });
  });

  it("returns an empty object for malformed JSON or a missing chip", () => {
    localStorage.setItem("qdash_metric_color_ranges:chipA", "{not json");
    expect(getStoredColorRanges("chipA")).toEqual({});
    expect(getStoredColorRanges("")).toEqual({});
  });

  it("removes the key when the last override is cleared", () => {
    setStoredColorRanges("chipA", { t1: { min: 10, max: 120 } });
    setStoredColorRanges("chipA", {});
    expect(localStorage.getItem("qdash_metric_color_ranges:chipA")).toBeNull();
  });
});

describe("resolveMetricColorRange", () => {
  it("returns null without numeric data", () => {
    expect(resolveMetricColorRange([null, undefined], null, 1, null)).toBeNull();
  });

  it("uses the data extent when nothing else is configured", () => {
    const resolved = resolveMetricColorRange([10, 50, 30], null, 1, null);
    expect(resolved).toEqual({
      effective: { min: 10, max: 50 },
      defaultRange: { min: 10, max: 50 },
      bounds: { min: 10, max: 50 },
      isOverridden: false,
    });
  });

  it("scales the YAML default into display units and widens the bounds to it", () => {
    const resolved = resolveMetricColorRange([95, 98], { min: 0.9, max: 0.999 }, 100, null);
    expect(resolved?.effective).toEqual({ min: 90, max: 99.9 });
    expect(resolved?.defaultRange).toEqual({ min: 90, max: 99.9 });
    expect(resolved?.bounds).toEqual({ min: 90, max: 99.9 });
    expect(resolved?.isOverridden).toBe(false);
  });

  it("prefers a valid override and reports it", () => {
    const resolved = resolveMetricColorRange([10, 50], null, 1, {
      min: 20,
      max: 40,
    });
    expect(resolved?.effective).toEqual({ min: 20, max: 40 });
    expect(resolved?.bounds).toEqual({ min: 10, max: 50 });
    expect(resolved?.isOverridden).toBe(true);
  });

  it("ignores an invalid override", () => {
    const resolved = resolveMetricColorRange([10, 50], null, 1, {
      min: 40,
      max: 20,
    });
    expect(resolved?.effective).toEqual({ min: 10, max: 50 });
    expect(resolved?.isOverridden).toBe(false);
  });
});
