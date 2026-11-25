import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TransformStepOutcome } from "@/components/features/execution/TransformStepOutcome";
import { isTransformExecution, transformRecordOf, transformSummary } from "@/lib/transformStep";

afterEach(cleanup);

const FILTER_NOTE = {
  step_kind: "transform",
  step_type: "FilterByMetric",
  transform_result: {
    kind: "filter",
    input_qids: ["0", "1", "2"],
    output_qids: ["0"],
    excluded: [
      { target: "1", reason: "t1 = 12 < 30" },
      { target: "2", reason: "metric t1 is missing" },
    ],
    criteria: "step check: t1 >= 30",
    source_step: "check",
    metric: "t1",
    threshold: 30,
    source_found: true,
  },
};

describe("transform step records", () => {
  it("reads only what the execution recorded", () => {
    expect(isTransformExecution(FILTER_NOTE)).toBe(true);
    // Executions recorded before transforms had their own carry no marker.
    expect(isTransformExecution({ step_index: 2 })).toBe(false);
    expect(transformRecordOf({ step_kind: "transform" })).toBeNull();
    expect(transformRecordOf({ transform_result: { output_qids: [] } })).toBeNull();
  });

  it("summarizes filters, missing sources and schedules", () => {
    expect(transformSummary(transformRecordOf(FILTER_NOTE)!)).toBe("Kept 1 of 3 qubits");
    expect(
      transformSummary({
        kind: "filter",
        input_qids: ["0"],
        output_qids: ["0"],
        source_found: false,
        message: "No one-qubit result to filter by; every candidate was kept",
      }),
    ).toBe("No one-qubit result to filter by; every candidate was kept");
    expect(
      transformSummary({
        kind: "cr_schedule",
        groups: [],
        message: "Fewer than 2 candidate qubits (1)",
      }),
    ).toBe("Fewer than 2 candidate qubits (1)");
    expect(transformSummary({ kind: "filter", input_qids: [], output_qids: [] })).toBe(
      "Kept 0 of 0 qubits",
    );
  });
});

describe("TransformStepOutcome", () => {
  it("lists each excluded qubit with its recorded reason", () => {
    render(<TransformStepOutcome note={FILTER_NOTE} status="completed" />);
    const outcome = screen.getByRole("region", { name: "Step outcome" });
    expect(within(outcome).getByText("FilterByMetric")).toBeTruthy();
    expect(within(outcome).getByText("Kept 1 of 3 qubits")).toBeTruthy();
    expect(within(outcome).getByText("step check: t1 >= 30")).toBeTruthy();
    const rows = within(outcome).getAllByRole("row").slice(1);
    expect(rows.map((row) => row.textContent)).toEqual(["1t1 = 12 < 30", "2metric t1 is missing"]);
  });

  it("lists the CR groups of a schedule in order", () => {
    render(
      <TransformStepOutcome
        note={{
          step_kind: "transform",
          step_type: "GenerateCRSchedule",
          transform_result: {
            kind: "cr_schedule",
            groups: [["0-1", "2-3"], ["4-5"]],
            direction: "forward",
            max_parallel_ops: 10,
          },
        }}
        status="completed"
      />,
    );
    expect(screen.getByText("3 pairs in 2 groups")).toBeTruthy();
    const groups = screen.getByRole("list", { name: "CR groups" });
    expect(
      within(groups)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Group 1: 0-1, 2-3", "Group 2: 4-5"]);
  });

  it("does not invent an outcome for a step that failed before recording one", () => {
    render(
      <TransformStepOutcome
        note={{ step_kind: "transform", step_type: "FilterByStatus" }}
        status="failed"
      />,
    );
    expect(screen.getByText(/ended before recording an outcome/)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
