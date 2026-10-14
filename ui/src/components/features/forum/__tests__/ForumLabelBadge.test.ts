import { describe, expect, it } from "vitest";

import type { ForumLabelDefinition } from "../categories";
import { getForumMarkerStyle, getReadableTextColor } from "../ForumLabelBadge";

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

describe("getForumMarkerStyle", () => {
  const labels: ForumLabelDefinition[] = [
    {
      id: "anomaly",
      label: "Anomaly",
      description: "Unexpected behavior",
      color: "#f59e0b",
    },
  ];

  it("returns undefined when no label key is linked", () => {
    expect(getForumMarkerStyle(undefined, labels)).toBeUndefined();
    expect(getForumMarkerStyle(null, labels)).toBeUndefined();
    expect(getForumMarkerStyle("", labels)).toBeUndefined();
  });

  it("resolves the background color and a readable text color for a known label", () => {
    expect(getForumMarkerStyle("anomaly", labels)).toEqual({
      backgroundColor: "#f59e0b",
      color: getReadableTextColor("#f59e0b"),
    });
  });

  it("falls back to the neutral color for an unknown label key", () => {
    expect(getForumMarkerStyle("deprecated", labels)).toEqual({
      backgroundColor: "#6b7280",
      color: getReadableTextColor("#6b7280"),
    });
  });

  it("defaults to an empty label list when none is provided", () => {
    expect(getForumMarkerStyle("deprecated")).toEqual({
      backgroundColor: "#6b7280",
      color: getReadableTextColor("#6b7280"),
    });
  });
});
