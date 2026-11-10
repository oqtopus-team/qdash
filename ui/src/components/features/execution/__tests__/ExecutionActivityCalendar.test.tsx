import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionActivityCalendar } from "@/components/features/execution/ExecutionActivityCalendar";

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

const ZERO = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };

function bucket(date: string, counts: Partial<Record<string, number>> = {}) {
  const merged = { ...ZERO, ...counts };
  return {
    date,
    start: new Date(`${date}T00:00:00+09:00`).toISOString(),
    end: new Date(Date.parse(`${date}T00:00:00+09:00`) + 86_400_000).toISOString(),
    ...merged,
    total: Object.values(merged).reduce((a, b) => a + b, 0),
  };
}

/** `days` daily buckets ending Monday 2026-11-02, with the given counts. */
function activity(days: number, counts: Record<string, Partial<Record<string, number>>> = {}) {
  const end = Date.UTC(2026, 10, 2);
  const buckets = Array.from({ length: days }, (_, offset) => {
    const date = new Date(end - (days - 1 - offset) * 86_400_000).toISOString().slice(0, 10);
    return bucket(date, counts[date]);
  });
  return {
    chip_id: "64Q",
    days,
    timezone: "Asia/Tokyo",
    granularity: "day",
    since: buckets[0].date,
    until: buckets[days - 1].date,
    buckets,
  };
}

const COUNTS = {
  "2026-10-29": { completed: 3, failed: 1 },
  "2026-11-01": { completed: 120, running: 4 },
  "2026-11-02": { scheduled: 2 },
};

afterEach(() => {
  cleanup();
  mocks.activity = null;
  mocks.state = { isLoading: false, isError: false };
});

function renderCalendar(overrides: Partial<Parameters<typeof ExecutionActivityCalendar>[0]> = {}) {
  const props = {
    chipId: "64Q",
    days: 90 as const,
    onDaysChange: vi.fn(),
    selectedDate: "latest",
    onDateSelect: vi.fn(),
    ...overrides,
  };
  const view = render(<ExecutionActivityCalendar {...props} />);
  return { props, view };
}

const grid = () => screen.getByRole("group", { name: /Executions per day/ });

function dayButton(date: string) {
  const button = within(grid())
    .getAllByRole("button")
    .find((item) => item.dataset.date === date);
  if (!button) throw new Error(`No day for ${date}`);
  return button;
}

describe("ExecutionActivityCalendar", () => {
  it("requests daily buckets for the chip over the chosen window", () => {
    mocks.activity = activity(90, COUNTS);
    renderCalendar();

    expect(mocks.lastParams).toMatchObject({ chip_id: "64Q", days: 90, granularity: "day" });
    expect(within(grid()).getAllByRole("button")).toHaveLength(90);
    expect(screen.getByText("130 in the last 90 days, 1 failed, 4 in progress.")).toBeTruthy();
  });

  it("offers 30, 90 and 365 day windows", () => {
    mocks.activity = activity(90, COUNTS);
    const { props } = renderCalendar();

    const tabs = within(screen.getByRole("tablist", { name: "Activity window" })).getAllByRole(
      "tab",
    );
    expect(tabs.map((tab) => tab.textContent)).toEqual(["30d", "90d", "365d"]);
    expect(tabs[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.click(tabs[2]);
    expect(props.onDaysChange).toHaveBeenCalledWith(365);
  });

  it("draws weekday and month labels, five legend levels, and volume-only colors", () => {
    mocks.activity = activity(90, COUNTS);
    renderCalendar();

    expect(screen.getAllByText("Mon").length).toBeGreaterThan(0);
    expect(screen.getByText("Wed")).toBeTruthy();
    expect(screen.getByText("Fri")).toBeTruthy();
    expect(screen.getByText("Sep")).toBeTruthy();
    const legend = screen.getByTestId("activity-heatmap-legend");
    expect(legend).toHaveTextContent(/^Less.*More$/);
    expect(
      within(screen.getByRole("list", { name: "Executions per day, by color" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(5);
    expect(dayButton("2026-10-29").dataset.level).toBe("1");
    expect(dayButton("2026-11-01").dataset.level).toBe("4");
    expect(dayButton("2026-10-30").dataset.level).toBe("0");
  });

  it("colors a count the same way in a 30-day and a 365-day window", () => {
    mocks.activity = activity(30, COUNTS);
    const { view, props } = renderCalendar({ days: 30 });
    const narrow = dayButton("2026-10-29").className;

    mocks.activity = activity(365, { ...COUNTS, "2026-03-01": { completed: 4000 } });
    view.rerender(<ExecutionActivityCalendar {...props} days={365} />);

    expect(dayButton("2026-10-29").className).toBe(narrow);
    expect(dayButton("2026-03-01").dataset.level).toBe("4");
  });

  it("names each day with its date and exact counts, and lists non-zero statuses in a tooltip", async () => {
    mocks.activity = activity(90, COUNTS);
    renderCalendar();

    expect(dayButton("2026-10-29")).toHaveAccessibleName(
      "Thu, Oct 29, 2026: 4 executions, 3 completed, 1 failed",
    );
    expect(dayButton("2026-10-30")).toHaveAccessibleName("Fri, Oct 30, 2026: 0 executions");

    fireEvent.focus(dayButton("2026-10-29"));
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Thu, Oct 29, 2026");
    expect(tooltip).toHaveTextContent("4 executions");
    expect(tooltip).toHaveTextContent("Completed3");
    expect(tooltip).toHaveTextContent("Failed1");
    expect(tooltip).not.toHaveTextContent("Running");
    expect(tooltip).not.toHaveTextContent("Cancelled");
    expect(tooltip).toHaveTextContent("Select to show Oct 29 in the list");
  });

  it("selects a day and clears the selection when it is selected again", () => {
    mocks.activity = activity(90, COUNTS);
    const { props, view } = renderCalendar();

    fireEvent.click(dayButton("2026-10-29"));
    expect(props.onDateSelect).toHaveBeenLastCalledWith("20261029");

    view.rerender(<ExecutionActivityCalendar {...props} selectedDate="20261029" />);
    expect(dayButton("2026-10-29").getAttribute("aria-pressed")).toBe("true");
    expect(dayButton("2026-10-29").className).toContain("ring-2");
    expect(dayButton("2026-10-29").tabIndex).toBe(0);
    expect(
      screen.getByText(/Showing Thu, Oct 29, 2026 in the list\. Select it again/),
    ).toBeTruthy();

    fireEvent.click(dayButton("2026-10-29"));
    expect(props.onDateSelect).toHaveBeenLastCalledWith("latest");
  });

  it("keeps a selected day outside the window and offers to show the latest", () => {
    mocks.activity = activity(30, COUNTS);
    const { props } = renderCalendar({ days: 30, selectedDate: "20260601" });

    expect(
      screen.getByText(/Showing Mon, Jun 1, 2026 in the list, outside this range/),
    ).toBeTruthy();
    expect(
      within(grid())
        .getAllByRole("button")
        .filter((button) => button.getAttribute("aria-pressed") === "true"),
    ).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Show latest" }));
    expect(props.onDateSelect).toHaveBeenCalledWith("latest");
  });

  it("moves by day and week with arrow keys from a single tab stop", () => {
    mocks.activity = activity(90, COUNTS);
    renderCalendar();

    const buttons = within(grid()).getAllByRole("button");
    expect(buttons.filter((button) => button.tabIndex === 0)).toEqual([dayButton("2026-11-02")]);

    dayButton("2026-11-02").focus();
    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(dayButton("2026-11-01"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(dayButton("2026-10-25"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(document.activeElement).toBe(dayButton("2026-11-01"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(document.activeElement).toBe(dayButton("2026-11-02"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(dayButton("2026-11-02"));
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement).toBe(dayButton("2026-08-05"));
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement).toBe(dayButton("2026-11-02"));
  });

  it("scrolls wide windows horizontally", () => {
    mocks.activity = activity(365, COUNTS);
    renderCalendar({ days: 365 });

    expect(screen.getByTestId("activity-heatmap-scroll").className).toContain("overflow-x-auto");
    expect(within(grid()).getAllByRole("button")).toHaveLength(365);
  });

  it("shows a skeleton while loading", () => {
    mocks.state = { isLoading: true, isError: false };
    renderCalendar();

    expect(document.querySelector(".skeleton")).not.toBeNull();
    expect(screen.getByText("Loading")).toBeTruthy();
  });

  it("shows an empty state instead of a heatmap when nothing ran", () => {
    mocks.activity = activity(90);
    renderCalendar();

    expect(screen.getByText("No executions in the last 90 days")).toBeTruthy();
    expect(screen.queryByRole("group", { name: /Executions per day/ })).toBeNull();
  });

  it("reports a load failure", () => {
    mocks.state = { isLoading: false, isError: true };
    renderCalendar();

    expect(screen.getByRole("alert")).toHaveTextContent("Execution activity could not be loaded.");
  });
});
