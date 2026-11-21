import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CouplingMetricGrid } from "../CouplingMetricGrid";
import { QubitMetricGrid } from "../QubitMetricGrid";

vi.mock("@/hooks/useTopologyConfig", () => ({
  useTopologyConfig: () => ({
    muxSize: 2,
    hasMux: false,
    layoutType: "grid",
    qubits: { 0: { row: 0, col: 0 }, 1: { row: 0, col: 1 } },
    couplings: [[0, 1]],
    gridSize: 2,
  }),
}));

const pinnedNote = {
  targetId: "0",
  content: "Drifting since the last cooldown",
  username: "alice",
  updatedAt: "2026-11-01T00:00:00Z",
};

describe("metric grid tooltips", () => {
  afterEach(cleanup);

  it("shows the qubit value and pinned summary when a cell receives keyboard focus", () => {
    render(
      <QubitMetricGrid
        metricData={{ "0": { value: 12.3456 } }}
        unit="us"
        topologyId="square"
        colors={["#000000", "#ffffff"]}
        targetNotedQids={new Set(["0"])}
        targetNotesByTarget={{ "0": pinnedNote }}
        metricKey="t1"
        onQubitClick={vi.fn()}
      />,
    );

    const cell = screen.getByRole("button", { name: /^0: 12\.3456 us/ });
    fireEvent.focus(cell);

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toContain("Q0: 12.3456 us");
    expect(tooltip.textContent).toContain("Drifting since the last cooldown");
    expect(cell.getAttribute("aria-describedby")).toBe(tooltip.id);

    fireEvent.keyDown(cell, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("shows only the value header for a coupling without notes", () => {
    render(
      <CouplingMetricGrid
        metricData={{ "0-1": { value: 0.9912 } }}
        unit="%"
        topologyId="square"
        colors={["#000000", "#ffffff"]}
        metricKey="cz_fidelity"
        onCouplingClick={vi.fn()}
      />,
    );

    fireEvent.focus(screen.getByRole("button", { name: /^Q0→Q1: 0\.9912 %/ }));

    expect(screen.getByRole("tooltip").textContent).toBe("Q0 → Q1: 0.9912 %");
  });
});
