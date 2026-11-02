import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MetricsStatsCards } from "@/components/features/metrics/MetricsStatsCards";

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

  it("shows final values on first render with a neutral maximum", () => {
    render(
      <MetricsStatsCards
        metricData={{ "0": { value: 12.345 }, "1": { value: 0.0123 }, "2": { value: 2500 } }}
        title="T1"
        unit="us"
        gridSize={2}
        metricType="qubit"
      />,
    );

    const valueOf = (title: string) =>
      screen.getByText(title).parentElement?.querySelector(".stat-value");

    expect(valueOf("Minimum")?.textContent).toBe("0.012");
    expect(valueOf("Median T1")?.textContent).toBe("12.35");
    expect(valueOf("Maximum")?.textContent).toBe((2500).toLocaleString());
    expect(valueOf("Maximum")?.className).not.toContain("text-success");
  });
});
