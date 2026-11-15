import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FlowExecutionPlanState } from "@/hooks/useFlowExecutionPlan";

import { FlowExecutionPreview } from "../FlowExecutionPreview";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const state: FlowExecutionPlanState = {
  status: "ready",
  plan: {
    flow_name: "f",
    chip_id: "c",
    source_updated_at: "2026-11-01T00:00:00",
    status: "resolved",
    runs: [
      {
        targets: null,
        steps: [
          {
            index: 1,
            type: "CustomTwoQubit",
            name: "cr",
            scope: "coupling",
            execution_mode: "manual",
            schedule: "manual",
            rounds: [
              { number: 1, targets: ["0-1", "4-5"] },
              { number: 2, targets: ["8-9"] },
            ],
            tasks: ["CheckCrossResonance", "CreateZX90"],
            summary: "Runs 2 rounds in the order written.",
            issues: [],
            unchecked: ["the step's current qubits depend on earlier steps"],
          },
          {
            index: 2,
            type: "TwoQubitCalibration",
            name: "two_qubit_calibration",
            scope: "coupling",
            execution_mode: "automatic",
            schedule: "automatic",
            rounds: [],
            tasks: null,
            summary: "Pairs are generated at run time.",
          },
        ],
      },
    ],
  },
};

describe("FlowExecutionPreview", () => {
  it("lists exact rounds, tasks and what is decided at run time", () => {
    render(<FlowExecutionPreview state={state} />);
    expect(screen.getByText(/Computed at run time/)).toBeInTheDocument();
    expect(screen.getByText("CheckCrossResonance → CreateZX90")).toBeInTheDocument();
    expect(screen.getByText("set at run time")).toBeInTheDocument();
    expect(screen.getByText("Automatic · formed at run time")).toBeInTheDocument();
    expect(screen.getByText("0-1, 4-5")).toBeInTheDocument();
    expect(screen.getByText(/Checked when the run starts instead/)).toBeInTheDocument();
    expect(screen.getByText(/does not promise\s+simultaneous measurements/)).toBeInTheDocument();
    expect(screen.queryByText(/Prefect/)).not.toBeInTheDocument();
  });

  it("plays the round order only on request and without durations", () => {
    vi.useFakeTimers();
    render(<FlowExecutionPreview state={state} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.some((row) => row.getAttribute("aria-current"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Play round order" }));
    expect(rows[0]).toHaveAttribute("aria-current", "step");
    act(() => vi.advanceTimersByTime(1200));
    expect(rows[1]).toHaveAttribute("aria-current", "step");
    act(() => vi.advanceTimersByTime(1200));
    expect(rows.some((row) => row.getAttribute("aria-current"))).toBe(false);
    expect(screen.getByRole("button", { name: "Play round order" })).toBeInTheDocument();
  });

  it("labels the bundled animation as an illustration and keeps it paused", () => {
    render(<FlowExecutionPreview state={state} />);
    expect(
      screen.getByText(/Illustrative example — not this run\. The sample/),
    ).toBeInTheDocument();
    const image = screen.getByRole("img");
    expect(image.getAttribute("src")).toMatch(/two-qubit-cr-schedule-poster\.png$/);
    fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
    expect(screen.getByRole("img").getAttribute("src")).toMatch(/two-qubit-cr-schedule\.gif$/);
  });

  it("reports an unavailable preview without blocking the run", () => {
    render(<FlowExecutionPreview state={{ status: "error", message: "Chip 'x' not found" }} />);
    expect(
      screen.getByText(/Execution preview unavailable: Chip 'x' not found/),
    ).toBeInTheDocument();
    expect(screen.getByText(/You can still run the flow/)).toBeInTheDocument();
  });
});
