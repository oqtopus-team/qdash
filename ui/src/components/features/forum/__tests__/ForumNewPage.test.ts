import { describe, expect, it } from "vitest";

import { parseLabels } from "../ForumNewPage";

describe("parseLabels", () => {
  it("parses a single comma-separated labels param", () => {
    expect(parseLabels(["a,b,c"])).toEqual(["a", "b", "c"]);
  });

  it("parses multiple labels params", () => {
    expect(parseLabels(["a", "b"])).toEqual(["a", "b"]);
  });

  it("trims whitespace around each label", () => {
    expect(parseLabels([" a , b "])).toEqual(["a", "b"]);
  });

  it("drops empty entries", () => {
    expect(parseLabels(["a,,b", "", " "])).toEqual(["a", "b"]);
  });

  it("dedupes labels across and within params", () => {
    expect(parseLabels(["a,b", "b,a,c"])).toEqual(["a", "b", "c"]);
  });

  it("returns an empty array when given no values", () => {
    expect(parseLabels([])).toEqual([]);
  });
});
