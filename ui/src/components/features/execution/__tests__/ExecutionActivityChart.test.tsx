import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionActivityChart } from "@/components/features/execution/ExecutionActivityChart";

const mocks = vi.hoisted(() => ({
  plotProps: null as Record<string, unknown> | null,
  activity: null as Record<string, unknown> | null,
  state: { isLoading: false, isError: false },
  lastParams: null as Record<string, unknown> | null,
}));

vi.mock("@/client/execution/execution", () => ({
  useGetExecutionActivity: (params: Record<string, unknown>) => {
    mocks.lastParams = params;
    return { data: mocks.activity ? { data: mocks.activity } : undefined, ...mocks.state };
  },
}));

vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));

vi.mock("@/components/charts/Plot", () => ({
  default: (props: Record<string, unknown>) => {
    mocks.plotProps = props;
    return <div data-testid="plot" />;
  },
}));

function bucket(date: string, counts: Partial<Record<string, number>> = {}) {
  const base = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };
  const merged = { ...base, ...counts };
  return { date, ...merged, total: Object.values(merged).reduce((a, b) => a + b, 0) };
}

const activity = {
  chip_id: "64Q",
  days: 7,
  timezone: "Asia/Tokyo",
  since: "2026-10-26",
  until: "2026-11-01",
  buckets: [
    bucket("2026-10-26"),
    bucket("2026-10-27", { completed: 2 }),
    bucket("2026-10-28"),
    bucket("2026-10-29", { failed: 1, completed: 1 }),
    bucket("2026-10-30"),
    bucket("2026-10-31", { running: 1 }),
    bucket("2026-11-01", { completed: 3 }),
  ],
};

afterEach(() => {
  cleanup();
  mocks.plotProps = null;
  mocks.activity = null;
  mocks.state = { isLoading: false, isError: false };
});

function renderChart(overrides: Partial<Parameters<typeof ExecutionActivityChart>[0]> = {}) {
  const props = {
    chipId: "64Q",
    days: 7 as const,
    onDaysChange: vi.fn(),
    selectedDate: "latest",
    onDateSelect: vi.fn(),
    ...overrides,
  };
  render(<ExecutionActivityChart {...props} />);
  return props;
}

describe("ExecutionActivityChart", () => {
  it("stacks one bar series per status that occurs in the window", () => {
    mocks.activity = activity;
    renderChart();

    const traces = mocks.plotProps?.data as Array<{ name: string; x: string[]; y: number[] }>;
    expect(traces.map((trace) => trace.name)).toEqual(["Completed", "Failed", "Running"]);
    expect(traces[0].x).toHaveLength(7);
    expect(traces[0].y).toEqual([0, 2, 0, 1, 0, 0, 3]);
    const layout = mocks.plotProps?.layout as { barmode: string };
    expect(layout.barmode).toBe("stack");
    expect(screen.getByText(/8 in the last 7 days, 1 failed, 1 in progress/)).toBeTruthy();
    expect(mocks.lastParams).toMatchObject({ chip_id: "64Q", days: 7 });
  });

  it("selects the clicked day and clears it when clicked again", () => {
    mocks.activity = activity;
    const props = renderChart();

    const onClick = mocks.plotProps?.onClick as (event: unknown) => void;
    onClick({ points: [{ x: "2026-10-29" }] });
    expect(props.onDateSelect).toHaveBeenCalledWith("20261029");

    cleanup();
    const again = renderChart({ selectedDate: "20261029" });
    const layout = mocks.plotProps?.layout as { shapes: Array<{ x0: string }> };
    expect(layout.shapes[0].x0).toBe("2026-10-29");
    const clickAgain = mocks.plotProps?.onClick as (event: unknown) => void;
    clickAgain({ points: [{ x: "2026-10-29" }] });
    expect(again.onDateSelect).toHaveBeenCalledWith("latest");
  });

  it("switches the window from the tabs", () => {
    mocks.activity = activity;
    const props = renderChart();

    fireEvent.click(screen.getByRole("tab", { name: "90d" }));

    expect(props.onDaysChange).toHaveBeenCalledWith(90);
    expect(screen.getByRole("tab", { name: "7d" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows an empty state instead of a chart when nothing ran", () => {
    mocks.activity = { ...activity, buckets: activity.buckets.map((b) => bucket(b.date)) };
    renderChart();

    expect(screen.getByText("No executions in the last 7 days")).toBeTruthy();
    expect(screen.queryByTestId("plot")).toBeNull();
  });

  it("reports a load failure", () => {
    mocks.state = { isLoading: false, isError: true };
    renderChart();

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
