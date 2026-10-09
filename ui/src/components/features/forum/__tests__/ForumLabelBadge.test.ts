import { describe, expect, it } from "vitest";

import { getReadableTextColor } from "../ForumLabelBadge";

describe("getReadableTextColor", () => {
  it("picks dark text for a light background", () => {
    expect(getReadableTextColor("#ffffff")).toBe("#111827");
  });

  it("picks white text for a dark background", () => {
    expect(getReadableTextColor("#000000")).toBe("#ffffff");
  });

  it("picks dark text for a light background given as a 3-digit shorthand", () => {
    expect(getReadableTextColor("#fff")).toBe("#111827");
  });

  it("picks white text for a dark background given as a 3-digit shorthand", () => {
    expect(getReadableTextColor("#000")).toBe("#ffffff");
  });

  it("works without a leading #", () => {
    expect(getReadableTextColor("ffffff")).toBe("#111827");
  });

  it("picks dark text for a light, saturated color", () => {
    expect(getReadableTextColor("#ffff00")).toBe("#111827");
  });

  it("picks white text for a dark, saturated color", () => {
    expect(getReadableTextColor("#000080")).toBe("#ffffff");
  });

  it("falls back to white text for an invalid hex value", () => {
    expect(getReadableTextColor("not-a-color")).toBe("#ffffff");
  });

  it("falls back to white text for a hex value of the wrong length", () => {
    expect(getReadableTextColor("#abcd")).toBe("#ffffff");
  });

  it("trims surrounding whitespace before validating", () => {
    expect(getReadableTextColor(" #ffffff ")).toBe("#111827");
  });
});
