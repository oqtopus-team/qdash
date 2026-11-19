import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CollisionCellResponse, CollisionEvaluateResponse } from "@/schemas";

import { CollisionMap, NOT_EVALUATED_COLOR } from "../panels/CollisionMap";

vi.mock("@/hooks/useTopologyConfig", () => ({
  useTopologyConfig: () => ({
    qubits: {
      0: { row: 0, col: 0 },
      1: { row: 0, col: 1 },
      2: { row: 1, col: 0 },
      3: { row: 1, col: 1 },
    },
    gridSize: 2,
    muxGroups: [],
    hasMux: false,
    showMuxBoundaries: false,
    isLoading: false,
  }),
}));

const RED = "#dc2626";
const ORANGE = "#d97706";
const BLUE = "#2563eb";

const LEGEND = [
  { color: BLUE, label: "< 1×" },
  { color: ORANGE, label: "1× boundary" },
  { color: RED, label: "> 1× exceeded" },
  { color: NOT_EVALUATED_COLOR, label: "Not evaluated" },
];

function cell(overrides: Partial<CollisionCellResponse>): CollisionCellResponse {
  return {
    key: "Q0",
    qid: null,
    source: null,
    target: null,
    hops: null,
    value: null,
    color: NOT_EVALUATED_COLOR,
    label: "Not evaluated",
    checks: [],
    estimates: [],
    ...overrides,
  };
}

function response(
  target: "qubit" | "pair",
  cells: CollisionCellResponse[],
): CollisionEvaluateResponse {
  return {
    chip_id: "chip-1",
    check: target === "qubit" ? "Type0A" : "Type1A",
    title: target === "qubit" ? "Type0A — Qubit quality" : "Type1A — GE–GE proximity",
    description: "",
    target,
    unit: "dimensionless",
    legend: LEGEND,
    parameters: {},
    cells,
    evaluated_at: "2026-11-19T00:00:00Z",
  };
}

describe("CollisionMap", () => {
  afterEach(() => {
    cleanup();
  });

  it("fills each qubit with its cell colour and greys out qubits without a cell", () => {
    const onSelectCell = vi.fn();
    const cells = [
      cell({ key: "Q0", qid: "0", value: 1.234, color: RED, label: "1.23× exceeded" }),
      cell({ key: "Q1", qid: "1", value: 0.5, color: BLUE, label: "0.50× within limit" }),
      cell({ key: "Q2", qid: "2", value: 1, color: ORANGE, label: "1.00× boundary" }),
    ];
    render(
      <CollisionMap
        response={response("qubit", cells)}
        topologyId="topo"
        onSelectCell={onSelectCell}
      />,
    );

    expect(screen.getByTestId("collision-qubit-0")).toHaveAttribute("fill", RED);
    expect(screen.getByTestId("collision-qubit-1")).toHaveAttribute("fill", BLUE);
    expect(screen.getByTestId("collision-qubit-2")).toHaveAttribute("fill", ORANGE);
    expect(screen.getByTestId("collision-qubit-3")).toHaveAttribute("fill", NOT_EVALUATED_COLOR);
    expect(screen.getByText("1.23")).toBeInTheDocument();
    expect(screen.queryAllByTestId(/^collision-edge-/)).toHaveLength(0);

    // Legend counts: one per colour, the missing qubit counts as not evaluated.
    const legend = screen.getByText("Not evaluated").closest("li");
    expect(legend).toHaveTextContent("Not evaluated1");

    fireEvent.click(screen.getByRole("button", { name: "Q0: 1.23× exceeded" }));
    expect(onSelectCell).toHaveBeenCalledWith(cells[0]);
  });

  it("draws one directed edge per pair cell, dashed for two-hop pairs", () => {
    const onSelectCell = vi.fn();
    const cells = [
      cell({ key: "0-1", source: "0", target: "1", hops: 1, value: 0.4, color: BLUE }),
      cell({ key: "1-0", source: "1", target: "0", hops: 1, value: 1.4, color: RED }),
      cell({ key: "0-2", source: "0", target: "2", hops: 1, value: 0.2, color: BLUE }),
      cell({ key: "0-3", source: "0", target: "3", hops: 2, value: null }),
    ];
    render(
      <CollisionMap
        response={response("pair", cells)}
        topologyId="topo"
        onSelectCell={onSelectCell}
      />,
    );

    const edges = screen.getAllByTestId(/^collision-edge-/);
    expect(edges).toHaveLength(cells.length);
    expect(screen.getByTestId("collision-edge-1-0")).toHaveAttribute("stroke", RED);
    expect(screen.getByTestId("collision-edge-0-1")).not.toHaveAttribute("stroke-dasharray");
    expect(screen.getByTestId("collision-edge-0-3")).toHaveAttribute("stroke-dasharray");
    // Pair maps draw qubits as neutral tiles, not coloured cells.
    expect(screen.queryByTestId("collision-qubit-0")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Forward" }));
    expect(screen.queryByTestId("collision-edge-1-0")).not.toBeInTheDocument();
    expect(screen.getAllByTestId(/^collision-edge-/)).toHaveLength(3);

    fireEvent.keyDown(screen.getByRole("button", { name: /^Q0 to Q1/ }), { key: "Enter" });
    expect(onSelectCell).toHaveBeenCalledWith(cells[0]);
  });
});
