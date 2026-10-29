import { describe, expect, it } from "vitest";

import {
  colorRangeStep,
  formatRangeValue,
  getValueExtent,
  interpolateColor,
  isValidColorRange,
  pickColor,
  scaleColorRange,
  unionColorRanges,
} from "../color-scale";

const PALETTE = ["#000000", "#808080", "#ffffff"];

describe("interpolateColor", () => {
  it("returns the endpoints at factor 0 and 1", () => {
    expect(interpolateColor("#000000", "#ffffff", 0)).toBe("#000000");
    expect(interpolateColor("#000000", "#ffffff", 1)).toBe("#ffffff");
  });

  it("blends channels linearly", () => {
    expect(interpolateColor("#000000", "#ff0000", 0.5)).toBe("#800000");
  });
});

describe("pickColor", () => {
  it("returns null for an empty palette", () => {
    expect(pickColor(1, 0, 2, [])).toBeNull();
  });

  it("maps min and max to the palette ends", () => {
    expect(pickColor(0, 0, 10, PALETTE)).toBe("#000000");
    expect(pickColor(10, 0, 10, PALETTE)).toBe("#ffffff");
  });

  it("clamps values outside the range", () => {
    expect(pickColor(-5, 0, 10, PALETTE)).toBe("#000000");
    expect(pickColor(50, 0, 10, PALETTE)).toBe("#ffffff");
  });

  it("uses the top color when the range is degenerate", () => {
    expect(pickColor(3, 3, 3, PALETTE)).toBe("#ffffff");
  });

  it("interpolates between neighbouring palette stops", () => {
    expect(pickColor(2.5, 0, 10, PALETTE)).toBe("#404040");
  });
});

describe("getValueExtent", () => {
  it("ignores null, undefined and non-finite values", () => {
    expect(getValueExtent([null, 3, undefined, Number.NaN, -1, 7])).toEqual({
      min: -1,
      max: 7,
    });
  });

  it("returns null when nothing is numeric", () => {
    expect(getValueExtent([null, undefined])).toBeNull();
  });
});

describe("isValidColorRange", () => {
  it("accepts increasing finite bounds only", () => {
    expect(isValidColorRange({ min: 0, max: 1 })).toBe(true);
    expect(isValidColorRange({ min: 1, max: 1 })).toBe(false);
    expect(isValidColorRange({ min: 2, max: 1 })).toBe(false);
    expect(isValidColorRange({ min: Number.NaN, max: 1 })).toBe(false);
    expect(isValidColorRange(null)).toBe(false);
    expect(isValidColorRange("0-1")).toBe(false);
  });
});

describe("scaleColorRange", () => {
  it("scales both bounds", () => {
    expect(scaleColorRange({ min: 0.9, max: 0.99 }, 100)).toEqual({
      min: 90,
      max: 99,
    });
  });

  it("keeps min below max for a negative scale", () => {
    expect(scaleColorRange({ min: 1, max: 2 }, -1)).toEqual({
      min: -2,
      max: -1,
    });
  });
});

describe("unionColorRanges", () => {
  it("spans every given range and skips missing ones", () => {
    expect(unionColorRanges({ min: 5, max: 8 }, null, { min: 2, max: 6 })).toEqual({
      min: 2,
      max: 8,
    });
  });

  it("returns null when every range is missing", () => {
    expect(unionColorRanges(null, undefined)).toBeNull();
  });
});

describe("colorRangeStep", () => {
  it("rounds the span / 200 down to a power of ten", () => {
    expect(colorRangeStep({ min: 0, max: 200 })).toBe(1);
    expect(colorRangeStep({ min: 0, max: 100 })).toBe(0.1);
    expect(colorRangeStep({ min: 99, max: 99.9 })).toBe(0.001);
  });

  it("falls back to 1 for a degenerate span", () => {
    expect(colorRangeStep({ min: 1, max: 1 })).toBe(1);
  });
});

describe("formatRangeValue", () => {
  it("shows the decimals the step needs", () => {
    expect(formatRangeValue(99.1234, 0.001)).toBe("99.123");
    expect(formatRangeValue(150.4, 1)).toBe("150");
    expect(formatRangeValue(7.25, 0.1)).toBe("7.3");
  });
});
