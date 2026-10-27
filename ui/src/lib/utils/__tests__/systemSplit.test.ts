import { describe, expect, it } from "vitest";

import { formatSystemSplit, getRunErrorMessage, getSystemSplit } from "../systemSplit";

const splitError = {
  response: {
    data: {
      detail: {
        message: "Targets span Systems",
        code: "system_split_required",
        chip_id: "144Qv3",
        systems: { "144Qv3": ["0", "1"], "144Qv3-quel3": ["24"] },
      },
    },
  },
};

describe("getSystemSplit", () => {
  it("parses the 400 detail of a refused run", () => {
    expect(getSystemSplit(splitError)).toEqual({
      message: "Targets span Systems",
      chipId: "144Qv3",
      systems: { "144Qv3": ["0", "1"], "144Qv3-quel3": ["24"] },
    });
  });

  it("ignores other errors", () => {
    expect(getSystemSplit({ response: { data: { detail: "Chip not found" } } })).toBeNull();
    expect(getSystemSplit({ response: { data: { detail: { code: "other" } } } })).toBeNull();
    expect(getSystemSplit(new Error("network"))).toBeNull();
  });
});

describe("getRunErrorMessage", () => {
  it("lists every System with its targets", () => {
    const message = getRunErrorMessage(splitError, "Failed");
    expect(message).toBe(formatSystemSplit(getSystemSplit(splitError)!));
    expect(message).toContain("144Qv3: 0, 1");
    expect(message).toContain("144Qv3-quel3: 24");
    expect(message).toContain("Run one System at a time.");
  });

  it("falls back to the ordinary API message", () => {
    expect(getRunErrorMessage({ response: { data: { detail: "Chip not found" } } }, "Failed")).toBe(
      "Chip not found",
    );
    expect(getRunErrorMessage(null, "Failed")).toBe("Failed");
  });
});
