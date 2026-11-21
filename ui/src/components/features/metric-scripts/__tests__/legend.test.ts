import { describe, expect, it } from "vitest";

import {
  continuousColor,
  countByLegend,
  countByStatus,
  createCellColoring,
  NOT_EVALUATED_COLOR,
  readableTextColor,
} from "../render/legend";
import { qubitCell } from "./fixtures";

describe("continuousColor", () => {
  const stops = [
    { value: 99, color: "#0000ff" },
    { value: 90, color: "#ff0000" },
  ];

  it("clamps to the end stops and blends linearly in between, whatever the stop order", () => {
    expect(continuousColor(stops, 80)).toBe("#ff0000");
    expect(continuousColor(stops, 100)).toBe("#0000ff");
    // Halfway between 90 and 99.
    expect(continuousColor(stops, 94.5)).toBe("#800080");
  });

  it("uses a stop as it is when it is not a hex colour", () => {
    expect(
      continuousColor(
        [
          { value: 0, color: "red" },
          { value: 1, color: "#000000" },
        ],
        0.5,
      ),
    ).toBe("red");
  });
});

describe("createCellColoring", () => {
  it("prefers the colour the script returned", () => {
    const coloring = createCellColoring(
      {
        legend: { kind: "continuous", stops: [{ value: 0, color: "#000000" }] },
        cells: [qubitCell("0", { value: 5, color: "#123456" })],
      },
      [],
    );
    expect(coloring.colorOf(qubitCell("0", { value: 5, color: "#123456" }))).toBe("#123456");
  });

  it("uses the continuous legend in the metric unit before the palette", () => {
    const coloring = createCellColoring(
      {
        legend: {
          kind: "continuous",
          stops: [
            { value: 90, color: "#ff0000" },
            { value: 100, color: "#0000ff" },
          ],
        },
        cells: [qubitCell("0", { value: 100 })],
      },
      ["#000000", "#ffffff"],
    );
    expect(coloring.mode).toBe("continuous");
    expect(coloring.colorOf(qubitCell("0", { value: 100 }))).toBe("#0000ff");
  });

  it("spreads the metrics colour scale over the value range without a legend", () => {
    const cells = [qubitCell("0", { value: 10 }), qubitCell("1", { value: 20 })];
    const coloring = createCellColoring({ legend: null, cells }, ["#000000", "#ffffff"]);
    expect(coloring.mode).toBe("range");
    expect(coloring.range).toEqual({ min: 10, max: 20 });
    expect(coloring.colorOf(cells[0])).toBe("#000000");
    expect(coloring.colorOf(cells[1])).toBe("#ffffff");
  });

  it("draws cells without a value grey", () => {
    const coloring = createCellColoring({ legend: null, cells: [] }, []);
    expect(coloring.mode).toBe("none");
    expect(coloring.colorOf(qubitCell("0", { status: "missing" }))).toBe(NOT_EVALUATED_COLOR);
  });
});

describe("legend counts", () => {
  it("counts drawn colours per categorical entry, case-insensitively, plus extra cells", () => {
    const counts = countByLegend(
      [
        { color: "#2563EB", label: "OK" },
        { color: NOT_EVALUATED_COLOR, label: "Not evaluated" },
      ],
      ["#2563eb", "#2563eb", "#737373"],
      { [NOT_EVALUATED_COLOR]: 2 },
    );
    expect(counts.map((entry) => entry.count)).toEqual([2, 3]);
  });

  it("counts cells per status", () => {
    expect(
      countByStatus([
        qubitCell("0"),
        qubitCell("1", { status: "error" }),
        qubitCell("2", { status: "empty" }),
        qubitCell("3", { status: "error" }),
      ]),
    ).toEqual({ ok: 1, missing: 0, empty: 1, error: 2 });
  });
});

describe("readableTextColor", () => {
  it("picks dark text on light fills and white on dark ones", () => {
    expect(readableTextColor("#fde724")).toBe("#111827");
    expect(readableTextColor("#440154")).toBe("#ffffff");
  });
});
