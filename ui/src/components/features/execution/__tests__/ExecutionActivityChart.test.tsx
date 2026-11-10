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

const ZERO = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };

function withCounts(counts: Partial<Record<string, number>>) {
  const merged = { ...ZERO, ...counts };
  return { ...merged, total: Object.values(merged).reduce((a, b) => a + b, 0) };
}

/** A Tokyo wall-clock time as the API renders bucket boundaries: UTC. */
const tokyo = (local: string) => new Date(`${local}+09:00`).toISOString();

/** A daily bucket in Tokyo: local midnight to the next local midnight. */
function bucket(date: string, counts: Partial<Record<string, number>> = {}) {
  const next = new Date(Date.parse(`${date}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10);
  return {
    date,
    start: tokyo(`${date}T00:00:00`),
    end: tokyo(`${next}T00:00:00`),
    ...withCounts(counts),
  };
}

/** A 6-hour bucket in Tokyo starting at `hour` on `date`. */
function slot(date: string, hour: number, counts: Partial<Record<string, number>> = {}) {
  const pad = (value: number) => String(value).padStart(2, "0");
  const next =
    hour === 18
      ? `${new Date(Date.parse(`${date}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10)}T00`
      : `${date}T${pad(hour + 6)}`;
  return {
    date,
    start: tokyo(`${date}T${pad(hour)}:00:00`),
    end: tokyo(`${next}:00:00`),
    ...withCounts(counts),
  };
}

const activity = {
  chip_id: "64Q",
  days: 30,
  timezone: "Asia/Tokyo",
  granularity: "day",
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
    days: 30 as const,
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

/** The column of the 6-hour bucket starting at a Tokyo wall-clock time, e.g. 2026-11-04T06:00. */
function slotButton(local: string) {
  const start = tokyo(`${local}:00`);
  const button = dayButtons().find((item) => item.dataset.start === start);
  if (!button) throw new Error(`No column starting ${start}`);
  return button;
}

/** Date labels drawn under the columns. */
function dateLabels() {
  return Array.from(
    screen
      .getByRole("toolbar")
      .parentElement!.querySelectorAll("[aria-hidden='true'] > span > span"),
  ).map((label) => label.textContent);
}

/** Count guides on the y axis, bottom up. */
function guides() {
  return Array.from(
    screen.getByTestId("activity-y-axis").querySelectorAll<HTMLElement>("[data-guide]"),
  ).map((guide) => Number(guide.dataset.guide));
}

/** Seven days of 6-hour buckets ending with the 12:00 bucket of 2026-11-04 (28 buckets). */
function sixHourActivity(counts: Record<string, Partial<Record<string, number>>> = {}) {
  const buckets = [];
  for (let index = 27; index >= 0; index -= 1) {
    const at = Date.parse("2026-11-04T12:00:00Z") - index * 6 * 3_600_000;
    const date = new Date(at).toISOString().slice(0, 10);
    const hour = new Date(at).getUTCHours();
    buckets.push(slot(date, hour, counts[`${date} ${hour}`] ?? {}));
  }
  return {
    ...activity,
    days: 7,
    granularity: "6h",
    since: buckets[0].date,
    until: "2026-11-04",
    buckets,
  };
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
    expect(screen.getByText(/8 in the last 30 days, 1 failed, 1 in progress/)).toBeTruthy();
    const legend = screen.getByRole("list", { name: "Executions by status" });
    expect(legend).toHaveTextContent("Completed 6");
    expect(legend).toHaveTextContent("Failed 1");
    expect(legend).toHaveTextContent("Running 1");
    expect(legend).not.toHaveTextContent("Scheduled");
    expect(mocks.lastParams).toMatchObject({ chip_id: "64Q", days: 30, granularity: "day" });
    expect(screen.getByRole("heading", { name: "Executions per day" })).toBeTruthy();
    expect(guides()).toEqual([0, 5, 10]);
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

  it("aggregates dense days into blocks whose filled height is exact", () => {
    mocks.activity = {
      ...activity,
      buckets: [
        bucket("2026-10-30", { completed: 3 }),
        bucket("2026-10-31", { completed: 37, failed: 3, cancelled: 1 }),
        bucket("2026-11-01", { completed: 120, running: 4 }),
      ],
    };
    renderChart();

    expect(screen.getByTestId("activity-scale")).toHaveTextContent(
      "1 block = 10 executions, a partly filled block holds fewer",
    );
    for (const button of dayButtons()) {
      expect(button.querySelectorAll("[data-block-executions]").length).toBeLessThanOrEqual(20);
    }
    expect(representedCounts("2026-10-31")).toEqual({ completed: 37, failed: 3, cancelled: 1 });
    expect(representedCounts("2026-11-01")).toEqual({ completed: 120, running: 4 });
    expect(representedCounts("2026-10-30")).toEqual({ completed: 3 });
    // 41 executions fill 4 blocks and a tenth of a fifth: statuses share blocks rather than
    // each rounding up, so the column is 4.1 blocks tall, not 6.
    const blocks = Array.from(
      dayButton("2026-10-31").querySelectorAll<HTMLElement>("[data-block-executions]"),
    );
    expect(blocks.map((block) => Number(block.dataset.blockExecutions))).toEqual([
      10, 10, 10, 10, 1,
    ]);
    const segments = (block: HTMLElement) =>
      Array.from(block.querySelectorAll<HTMLElement>("[data-status]")).map((segment) => [
        segment.dataset.status,
        Number(segment.dataset.executions),
        segment.style.height,
      ]);
    expect(segments(blocks[3])).toEqual([
      ["completed", 7, "70%"],
      ["failed", 3, "30%"],
    ]);
    expect(segments(blocks[4])).toEqual([["cancelled", 1, "10%"]]);
    // 124 executions need 12.4 blocks, so the grid grows to the next guide, 15 blocks.
    expect(dayButton("2026-11-01").querySelectorAll("[data-block-executions]")).toHaveLength(13);
    expect(guides()).toEqual([0, 50, 100, 150]);
    // Accessible names keep the exact count rather than the block count.
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

    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["7d", "30d", "90d"]);
    fireEvent.click(screen.getByRole("tab", { name: "7d" }));

    expect(props.onDaysChange).toHaveBeenCalledWith(7);
    expect(screen.getByRole("tab", { name: "30d" })).toHaveAttribute("aria-selected", "true");
  });

  it("draws every day of the 90-day window with sparse date labels", () => {
    const end = Date.UTC(2026, 10, 1);
    const dates = Array.from({ length: 90 }, (_, index) =>
      new Date(end - (89 - index) * 86_400_000).toISOString().slice(0, 10),
    );
    mocks.activity = {
      ...activity,
      days: 90,
      since: dates[0],
      until: dates[89],
      buckets: dates.map((date, index) =>
        bucket(date, index === 50 ? { completed: 230, failed: 4 } : { completed: index % 3 }),
      ),
    };
    renderChart({ days: 90 });

    expect(mocks.lastParams).toMatchObject({ chip_id: "64Q", days: 90, granularity: "day" });
    expect(dates[0]).toBe("2026-08-04");
    expect(dayButtons()).toHaveLength(90);
    expect(screen.getByRole("tab", { name: "90d" })).toHaveAttribute("aria-selected", "true");
    for (const button of dayButtons()) {
      expect(button.querySelectorAll("[data-block-executions]").length).toBeLessThanOrEqual(20);
    }
    expect(representedCounts(dates[50])).toEqual({ completed: 230, failed: 4 });
    // Every 15th day from the latest carries a date, so 90 columns show 6 labels.
    const labels = dateLabels();
    expect(labels).toHaveLength(6);
    expect(labels[labels.length - 1]).toBe("Nov 1");
    expect(labels[0]).toBe("Aug 18");
  });

  it("draws the 7-day window as 28 six-hour buckets labeled by day", () => {
    mocks.activity = sixHourActivity({
      "2026-11-04 6": { completed: 2, failed: 1 },
      "2026-11-03 18": { running: 1 },
    });
    renderChart({ days: 7 });

    expect(mocks.lastParams).toMatchObject({ chip_id: "64Q", days: 7, granularity: "6h" });
    expect(screen.getByRole("heading", { name: "Executions per 6 hours" })).toBeTruthy();
    expect(dayButtons()).toHaveLength(28);
    // Empty buckets keep their columns, so the timeline stays continuous.
    expect(dayButtons().filter((button) => button.querySelector("[data-status]"))).toHaveLength(2);
    expect(dayButtons()[0].dataset.start).toBe(tokyo("2026-10-28T18:00:00"));
    expect(dayButtons()[27].dataset.start).toBe(tokyo("2026-11-04T12:00:00"));
    // A date marks each day's first bucket; the oldest bucket starts at 18:00, so it has none.
    expect(dateLabels()).toEqual([
      "Oct 29",
      "Oct 30",
      "Oct 31",
      "Nov 1",
      "Nov 2",
      "Nov 3",
      "Nov 4",
    ]);
    expect(slotButton("2026-11-04T06:00")).toHaveAccessibleName(
      "Wed, Nov 4, 2026, 06:00–12:00: 3 executions, 2 completed, 1 failed",
    );
    expect(slotButton("2026-11-03T18:00")).toHaveAccessibleName(
      "Tue, Nov 3, 2026, 18:00–24:00: 1 execution, 1 running",
    );
    expect(screen.getByText(/4 in the last 7 days, 1 failed, 1 in progress/)).toBeTruthy();
    expect(guides()).toEqual([0, 5, 10]);
  });

  it("says a 6-hour bucket shows its whole day, and selects that day", async () => {
    mocks.activity = sixHourActivity({ "2026-11-04 6": { completed: 2 } });
    const props = renderChart({ days: 7 });

    fireEvent.focus(slotButton("2026-11-04T06:00"));
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Wed, Nov 4, 2026, 06:00–12:00");
    expect(tooltip).toHaveTextContent("Select to show all of Nov 4 in the list");
    expect(
      screen.getByText("Select a 6-hour bucket to show all executions of its day in the list."),
    ).toBeTruthy();

    fireEvent.click(slotButton("2026-11-04T06:00"));
    expect(props.onDateSelect).toHaveBeenCalledWith("20261104");

    cleanup();
    const again = renderChart({ days: 7, selectedDate: "20261104" });
    const pressed = dayButtons().filter((button) => button.getAttribute("aria-pressed") === "true");
    expect(pressed.map((button) => button.dataset.start)).toEqual([
      tokyo("2026-11-04T00:00:00"),
      tokyo("2026-11-04T06:00:00"),
      tokyo("2026-11-04T12:00:00"),
    ]);
    expect(screen.getByText(/Showing Wed, Nov 4, 2026 in the list/)).toBeTruthy();
    // Any bucket of the selected day clears the day filter.
    fireEvent.click(slotButton("2026-11-04T12:00"));
    expect(again.onDateSelect).toHaveBeenCalledWith("latest");
  });

  it("moves between 6-hour buckets with arrow keys from a single tab stop", () => {
    mocks.activity = sixHourActivity({ "2026-11-03 12": { completed: 1 } });
    renderChart({ days: 7, selectedDate: "20261103" });

    const tabbable = dayButtons().filter((button) => button.tabIndex === 0);
    expect(tabbable.map((button) => button.dataset.start)).toEqual([tokyo("2026-11-03T00:00:00")]);
    tabbable[0].focus();
    fireEvent.keyDown(tabbable[0], { key: "ArrowLeft" });
    expect(slotButton("2026-11-02T18:00")).toHaveFocus();
    fireEvent.keyDown(slotButton("2026-11-02T18:00"), { key: "End" });
    expect(slotButton("2026-11-04T12:00")).toHaveFocus();
  });

  it("shows the page's mode switch beside the window tabs", () => {
    mocks.activity = activity;
    renderChart({ modeSwitch: <button type="button">Activity</button> });

    expect(screen.getByRole("button", { name: "Activity" })).toBeTruthy();
    expect(screen.getByRole("tablist", { name: "Activity window" })).toBeTruthy();
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

    expect(screen.getByText("No executions in the last 30 days")).toBeTruthy();
    expect(screen.queryByRole("toolbar")).toBeNull();
  });

  it("reports a load failure", () => {
    mocks.state = { isLoading: false, isError: true };
    renderChart();

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
