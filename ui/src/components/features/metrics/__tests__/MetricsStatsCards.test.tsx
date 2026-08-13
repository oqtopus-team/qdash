import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetricsStatsCards } from "@/components/features/metrics/MetricsStatsCards";

vi.mock("@/components/ui/AnimatedCounter", () => ({
  AnimatedCounter: ({ value }: { value: number }) => <span>{value}</span>,
}));

describe("MetricsStatsCards", () => {
  afterEach(() => cleanup());

  it("distinguishes unavailable statistics from measured zero values", () => {
    render(
      <MetricsStatsCards
        metricData={{ "0": { value: null }, "1": { value: null } }}
        title="T1"
        unit="us"
        gridSize={2}
        metricType="qubit"
      />,
    );

    expect(screen.getAllByLabelText("No data")).toHaveLength(4);
    expect(screen.queryByText("0")).toBeNull();
  });

  it("calculates the median across an even number of values", () => {
    render(
      <MetricsStatsCards
        metricData={{ "0": { value: 1 }, "1": { value: 3 } }}
        title="T1"
        unit="us"
        gridSize={2}
        metricType="qubit"
      />,
    );

    expect(screen.getByText("Median T1").parentElement?.textContent).toContain("2");
  });
});
