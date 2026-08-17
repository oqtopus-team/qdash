import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardSummaryTable } from "@/components/features/dashboard/DashboardSummaryTable";

describe("DashboardSummaryTable", () => {
  it("shows coverage and calculates the median for an even number of values", () => {
    render(
      <DashboardSummaryTable
        rows={[
          {
            key: "t1",
            title: "T1",
            unit: "us",
            type: "Qubit",
            expectedTotal: 4,
            data: {
              "0": { value: 1 },
              "1": { value: 3 },
              "2": { value: null },
            },
          },
        ]}
      />,
    );

    expect(screen.getByText("50.0% (2/4)")).toBeTruthy();
    expect(screen.getByText("2.0000")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "T1 coverage" }).getAttribute("value")).toBe(
      "50",
    );
  });

  it("uses a dash for unavailable distribution values", () => {
    render(
      <DashboardSummaryTable
        rows={[
          {
            key: "fidelity",
            title: "Gate Fidelity",
            unit: "",
            type: "Coupling",
            expectedTotal: 2,
            data: null,
          },
        ]}
      />,
    );

    expect(screen.getByText("0.0% (0/2)")).toBeTruthy();
    expect(screen.getAllByText("—")).toHaveLength(3);
  });
});
