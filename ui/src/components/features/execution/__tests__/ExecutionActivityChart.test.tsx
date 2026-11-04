import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionActivityChart } from "@/components/features/execution/ExecutionActivityChart";

const mocks = vi.hoisted(() => ({
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

function dayButtons() {
  return within(screen.getByRole("toolbar")).getAllByRole("button");
}

function dayButton(date: string) {
  const button = dayButtons().find((item) => item.dataset.date === date);
  if (!button) throw new Error(`No column for ${date}`);
  return button;
}

/** Status of each filled block bottom-up, with the executions it stands for. */
function blocksOf(date: string) {
  return Array.from(dayButton(date).querySelectorAll<HTMLElement>("[data-status]")).map(
    (block) => ({
      status: block.dataset.status,
      executions: Number(block.dataset.executions),
      partial: block.dataset.partial === "true",
    }),
  );
}

/** Executions per status represented by a column's blocks. */
function representedCounts(date: string) {
  const counts: Record<string, number> = {};
  for (const block of blocksOf(date)) {
    counts[block.status ?? ""] = (counts[block.status ?? ""] ?? 0) + block.executions;
  }
  return counts;
}

describe("ExecutionActivityChart", () => {
  it("draws one block per execution, stacked by status, for every day in the window", () => {
    mocks.activity = activity;
    renderChart();

    expect(dayButtons()).toHaveLength(7);
    expect(blocksOf("2026-10-26")).toEqual([]);
    expect(blocksOf("2026-10-29")).toEqual([
      { status: "completed", executions: 1, partial: false },
      { status: "failed", executions: 1, partial: false },
    ]);
    expect(blocksOf("2026-11-01")).toHaveLength(3);
    expect(screen.getByTestId("activity-scale")).toHaveTextContent("1 block = 1 execution");
    expect(screen.getByText(/8 in the last 7 days, 1 failed, 1 in progress/)).toBeTruthy();
    const legend = screen.getByRole("list", { name: "Executions by status" });
    expect(legend).toHaveTextContent("Completed 6");
    expect(legend).toHaveTextContent("Failed 1");
    expect(legend).toHaveTextContent("Running 1");
    expect(legend).not.toHaveTextContent("Scheduled");
    expect(mocks.lastParams).toMatchObject({ chip_id: "64Q", days: 7 });
  });

  it("names each day with its date and per-status counts", () => {
    mocks.activity = activity;
    renderChart();

    expect(dayButton("2026-10-29")).toHaveAccessibleName(
      "Thu, Oct 29, 2026: 2 executions, 1 completed, 1 failed",
    );
    expect(dayButton("2026-10-26")).toHaveAccessibleName("Mon, Oct 26, 2026: 0 executions");
  });

  it("shows the hovered day's counts in a tooltip", async () => {
    mocks.activity = activity;
    renderChart();

    fireEvent.focus(dayButton("2026-10-29"));

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Thu, Oct 29, 2026");
    expect(tooltip).toHaveTextContent("2 executions");
    expect(tooltip).toHaveTextContent("Completed1");
    expect(tooltip).toHaveTextContent("Failed1");
  });

  it("aggregates dense days into labeled blocks that keep exact partial counts", () => {
    mocks.activity = {
      ...activity,
      buckets: [
        bucket("2026-10-30", { completed: 3 }),
        bucket("2026-10-31", { completed: 37, failed: 3, cancelled: 1 }),
        bucket("2026-11-01", { completed: 120, running: 4 }),
      ],
    };
    renderChart();

    for (const button of dayButtons()) {
      expect(button.querySelectorAll("[data-status]").length).toBeLessThanOrEqual(20);
    }
    expect(screen.getByTestId("activity-scale")).toHaveTextContent(
      "1 block = 10 executions, a lighter block holds fewer",
    );
    expect(representedCounts("2026-10-31")).toEqual({ completed: 37, failed: 3, cancelled: 1 });
    expect(representedCounts("2026-11-01")).toEqual({ completed: 120, running: 4 });
    expect(representedCounts("2026-10-30")).toEqual({ completed: 3 });
    expect(blocksOf("2026-10-31").filter((block) => block.partial)).toEqual([
      { status: "completed", executions: 7, partial: true },
      { status: "failed", executions: 3, partial: true },
      { status: "cancelled", executions: 1, partial: true },
    ]);
    // Accessible names keep the exact count rather than the rounded block count.
    expect(dayButton("2026-10-31")).toHaveAccessibleName(
      "Sat, Oct 31, 2026: 41 executions, 37 completed, 3 failed, 1 cancelled",
    );
  });

  it("selects the clicked day and clears it when clicked again", () => {
    mocks.activity = activity;
    const props = renderChart();

    fireEvent.click(dayButton("2026-10-29"));
    expect(props.onDateSelect).toHaveBeenCalledWith("20261029");

    cleanup();
    const again = renderChart({ selectedDate: "20261029" });
    expect(dayButton("2026-10-29")).toHaveAttribute("aria-pressed", "true");
    expect(dayButton("2026-10-27")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/Showing Thu, Oct 29, 2026 in the list/)).toBeTruthy();
    fireEvent.click(dayButton("2026-10-29"));
    expect(again.onDateSelect).toHaveBeenCalledWith("latest");
  });

  it("moves between days with arrow keys from a single tab stop", () => {
    mocks.activity = activity;
    const props = renderChart({ selectedDate: "20261029" });

    const tabbable = dayButtons().filter((button) => button.tabIndex === 0);
    expect(tabbable.map((button) => button.dataset.date)).toEqual(["2026-10-29"]);

    dayButton("2026-10-29").focus();
    fireEvent.keyDown(dayButton("2026-10-29"), { key: "ArrowRight" });
    expect(dayButton("2026-10-30")).toHaveFocus();
    fireEvent.keyDown(dayButton("2026-10-30"), { key: "Home" });
    expect(dayButton("2026-10-26")).toHaveFocus();
    fireEvent.keyDown(dayButton("2026-10-26"), { key: "ArrowLeft" });
    expect(dayButton("2026-10-26")).toHaveFocus();
    fireEvent.keyDown(dayButton("2026-10-26"), { key: "End" });
    expect(dayButton("2026-11-01")).toHaveFocus();
    expect(dayButton("2026-11-01").tabIndex).toBe(0);

    fireEvent.click(dayButton("2026-11-01"));
    expect(props.onDateSelect).toHaveBeenCalledWith("20261101");
  });

  it("switches the window from the tabs", () => {
    mocks.activity = activity;
    const props = renderChart();

    fireEvent.click(screen.getByRole("tab", { name: "90d" }));

    expect(props.onDaysChange).toHaveBeenCalledWith(90);
    expect(screen.getByRole("tab", { name: "7d" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows a skeleton while loading", () => {
    mocks.state = { isLoading: true, isError: false };
    renderChart();

    expect(screen.getByText("Loading")).toBeTruthy();
    expect(screen.queryByRole("toolbar")).toBeNull();
  });

  it("shows an empty state instead of a chart when nothing ran", () => {
    mocks.activity = { ...activity, buckets: activity.buckets.map((b) => bucket(b.date)) };
    renderChart();

    expect(screen.getByText("No executions in the last 7 days")).toBeTruthy();
    expect(screen.queryByRole("toolbar")).toBeNull();
  });

  it("reports a load failure", () => {
    mocks.state = { isLoading: false, isError: true };
    renderChart();

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
