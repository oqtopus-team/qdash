import { describe, expect, it } from "vitest";

import {
  convertSweep,
  describeSweep,
  expandSweep,
  formatSweepValue,
  isCompatibleValueType,
} from "../task-parameters";

describe("expandSweep", () => {
  it.each([
    ["np.linspace", [0, 1, 5], [0, 0.25, 0.5, 0.75, 1]],
    ["np.linspace", [3, 9, 1], [3]],
    ["np.logspace", [0, 2, 3], [1, 10, 100]],
    ["np.arange", [0, 1, 0.25], [0, 0.25, 0.5, 0.75]],
    ["np.arange", [5, 0, -2], [5, 3, 1]],
    ["range", [0, 41, 10], [0, 10, 20, 30, 40]],
    ["range", [10, 0, 5], []],
    ["list", [0, 4, 16], [0, 4, 16]],
  ] as const)("expands %s %j", (type, value, points) => {
    expect(expandSweep(type, value)).toEqual(points);
  });

  it.each([
    ["np.linspace", [0, 1, 0]],
    ["np.linspace", [0, 1, 2.5]],
    ["np.linspace", [0, 1]],
    ["np.arange", [0, 1, 0]],
    ["np.arange", [0, 1e9, 1]],
    ["range", [0, 10, 0.5]],
    ["range", "[0, 10, 2]"],
    ["list", [0, "a"]],
  ] as const)("rejects %s %j", (type, value) => {
    expect(expandSweep(type, value)).toBeNull();
  });
});

describe("convertSweep", () => {
  it.each([
    ["range", [0, 401, 8], "np.linspace", [0, 400, 51]],
    ["range", [0, 401, 8], "np.arange", [0, 401, 8]],
    ["np.arange", [0, 1, 0.25], "np.linspace", [0, 0.75, 4]],
    ["np.linspace", [0, 400, 11], "range", [0, 440, 40]],
    ["np.linspace", [0, 1, 11], "np.arange", [0, 1.1, 0.1]],
    // np.arange(1, 1.3, 0.1) lets a fourth point in, so the stop lands half a step past 1.2.
    ["np.linspace", [1, 1.2, 3], "np.arange", [1, 1.25, 0.1]],
    ["np.linspace", [7, 7, 1], "np.arange", [7, 8, 1]],
    ["np.arange", [5, 0, -2], "np.linspace", [5, 1, 3]],
    ["np.linspace", [5, 1, 3], "np.arange", [5, -1, -2]],
    ["np.logspace", [0, 2, 3], "np.linspace", [1, 100, 3]],
    ["np.linspace", [1, 1000, 4], "np.logspace", [0, 3, 4]],
    ["list", [0, 10, 20, 30, 40], "range", [0, 50, 10]],
    ["list", [1, 10, 100], "np.logspace", [0, 2, 3]],
    ["range", [0, 41, 10], "list", [0, 10, 20, 30, 40]],
  ] as const)("converts %s %j to %s", (from, value, to, expected) => {
    expect(convertSweep(from, value, to)).toEqual(expected);
  });

  it.each([
    ["np.linspace", [0, 1, 11], "range"],
    ["range", [0, 10, 2], "np.logspace"],
    ["range", [0, 10, 0], "np.linspace"],
    ["range", [10, 0, 5], "list"],
    ["np.linspace", [0, 1, 11], "np.linspace"],
  ] as const)("cannot convert %s %j to %s", (from, value, to) => {
    expect(convertSweep(from, value, to)).toBeNull();
  });

  it("regenerates the same points for the linear forms", () => {
    const points = expandSweep("range", [0, 401, 8]);
    const sources = {
      "np.linspace": [0, 400, 51],
      "np.arange": [0, 401, 8],
      range: [0, 401, 8],
      list: points,
    } as const;
    const forms = Object.keys(sources) as (keyof typeof sources)[];
    for (const from of forms) {
      for (const to of forms) {
        if (from === to) continue;
        const converted = convertSweep(from, sources[from], to);
        expect(converted, `${from} -> ${to}`).not.toBeNull();
        expect(expandSweep(to, converted), `${from} -> ${to}`).toEqual(points);
      }
    }
  });
});

describe("describeSweep", () => {
  it.each([
    ["range", [0, 401, 8], "51 points: 0 to 400"],
    ["np.logspace", [2, 5, 11], "11 points: 100 to 100000"],
    ["np.linspace", [0, 1, 3], "3 points: 0 to 1"],
    ["np.linspace", [7, 7, 1], "1 point: 7"],
    ["range", [10, 0, 5], "0 points"],
    ["range", [0, 10, 0], null],
  ] as const)("describes %s %j", (type, value, summary) => {
    expect(describeSweep(type, value)).toBe(summary);
  });
});

describe("isCompatibleValueType", () => {
  it.each([
    ["range", undefined, true],
    ["range", "np.linspace", true],
    ["np.logspace", "list", true],
    ["range", "float", false],
    ["int", "np.linspace", false],
    ["list", "np.arange", false],
    ["float", "int", true],
  ])("declared %s takes %s: %s", (declared, requested, expected) => {
    expect(isCompatibleValueType(declared, requested)).toBe(expected);
  });
});

describe("formatSweepValue", () => {
  it("shows a recorded sweep as its constructor call", () => {
    expect(formatSweepValue("np.linspace", [0, 1, 11])).toBe("np.linspace(0, 1, 11)");
  });
  it("leaves explicit values and scalars alone", () => {
    expect(formatSweepValue("list", [0, 1, 11])).toBeNull();
    expect(formatSweepValue("int", 11)).toBeNull();
  });
});
