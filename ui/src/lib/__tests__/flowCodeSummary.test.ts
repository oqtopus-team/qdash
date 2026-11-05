import { describe, expect, it } from "vitest";

import { formatMuxIds, summarizeFlowCode } from "@/lib/flowCodeSummary";

describe("summarizeFlowCode", () => {
  it("reads a multi-line task list and a range of MUX IDs", () => {
    const code = [
      "FAKE_CALIBRATION_TASKS: list[str] = [",
      '    "FakeBringUp",  # seeds the simulator',
      "    'CheckRabi',",
      "]",
      "# MUX 0 to 15",
      "MUX_IDS: list[int] = list(range(16))",
    ].join("\n");
    expect(summarizeFlowCode(code)).toEqual({
      tasks: ["FakeBringUp", "CheckRabi"],
      muxIds: Array.from({ length: 16 }, (_, index) => index),
    });
  });

  it("follows a user's edit to a MUX subset", () => {
    expect(summarizeFlowCode("MUX_IDS = [9, 15]\n").muxIds).toEqual([9, 15]);
    expect(summarizeFlowCode("MUX_IDS = list(range(4, 8))\n").muxIds).toEqual([4, 5, 6, 7]);
  });

  it("gives up on anything it cannot read literally", () => {
    expect(summarizeFlowCode("MUX_IDS = compute()\nX_TASKS = TASKS + ['A']\n")).toEqual({
      tasks: null,
      muxIds: null,
    });
    expect(summarizeFlowCode("def f():\n    MUX_IDS = [1]\n").muxIds).toBeNull();
  });
});

describe("formatMuxIds", () => {
  it("collapses runs and keeps gaps", () => {
    expect(formatMuxIds([0, 1, 2, 3, 9, 15])).toBe("MUX 0–3, 9, 15");
    expect(formatMuxIds([9, 15])).toBe("MUX 9, 15");
    expect(formatMuxIds([3, 4])).toBe("MUX 3, 4");
    expect(formatMuxIds([])).toBe("no MUX");
  });
});
