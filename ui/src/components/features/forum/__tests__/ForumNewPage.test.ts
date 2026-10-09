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

  it("limits the result to MAX_FORUM_POST_LABELS", () => {
    const values = Array.from({ length: 12 }, (_, index) => `label-${index}`);
    const result = parseLabels(values);
    expect(result).toHaveLength(10);
    expect(result).toEqual(values.slice(0, 10));
  });
});
