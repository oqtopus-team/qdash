import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HomeExecutionActivity } from "@/components/features/home/HomeExecutionActivity";

const mocks = vi.hoisted(() => ({
  activity: null as Record<string, unknown> | null,
  state: { isLoading: false, isError: false },
  lastParams: undefined as Record<string, unknown> | undefined,
}));

vi.mock("@/client/execution/execution", () => ({
  getGetExecutionActivityQueryKey: () => ["/executions/activity"],
  useGetExecutionActivity: (params?: Record<string, unknown>) => {
    mocks.lastParams = params;
    return { data: mocks.activity ? { data: mocks.activity } : undefined, ...mocks.state };
  },
}));

vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ projectId: "project-1" }) }));

function bucket(date: string, counts: Partial<Record<string, number>> = {}) {
  const base = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };
  const merged = { ...base, ...counts };
  return { date, ...merged, total: Object.values(merged).reduce((a, b) => a + b, 0) };
}

/** A 90-day window ending Monday 2026-11-02, with the given counts on chosen days. */
function quarter(counts: Record<string, Partial<Record<string, number>>> = {}) {
  const end = Date.UTC(2026, 10, 2);
  const buckets = Array.from({ length: 90 }, (_, offset) => {
    const date = new Date(end - (89 - offset) * 86_400_000).toISOString().slice(0, 10);
    return bucket(date, counts[date]);
  });
  return {
    chip_id: null,
    days: 90,
    timezone: "Asia/Tokyo",
    since: buckets[0].date,
    until: buckets[89].date,
    buckets,
  };
}

afterEach(() => {
  cleanup();
  mocks.activity = null;
  mocks.state = { isLoading: false, isError: false };
  mocks.lastParams = undefined;
});

const grid = () => screen.getByRole("group", { name: /Executions per day/ });

function dayLink(date: string) {
  const link = within(grid())
    .getAllByRole("link")
    .find((item) => item.dataset.date === date);
  if (!link) throw new Error(`No day for ${date}`);
  return link;
}

describe("HomeExecutionActivity", () => {
  it("requests the last 90 days for the whole project, not one chip", () => {
    mocks.activity = quarter();
    render(<HomeExecutionActivity />);

    expect(mocks.lastParams).toMatchObject({ days: 90 });
    expect(mocks.lastParams).not.toHaveProperty("chip_id");
  });

  it("summarizes the window and draws a compact heatmap of every day", () => {
    mocks.activity = quarter({
      "2026-11-01": { failed: 1, completed: 2 },
      "2026-11-02": { running: 1 },
    });
    render(<HomeExecutionActivity />);

    expect(screen.getByTestId("home-activity-total")).toHaveTextContent("4executions · 1 failed");
    const statuses = within(screen.getByRole("list", { name: "Executions by status" }));
    expect(statuses.getByText(/Completed/)).toHaveTextContent("Completed 2");
    expect(statuses.getByText(/Failed/)).toHaveTextContent("Failed 1");
    expect(statuses.queryByText(/Scheduled/)).toBeNull();
    expect(within(grid()).getAllByRole("link")).toHaveLength(90);
    expect(dayLink("2026-11-01").dataset.level).toBe("1");
    expect(dayLink("2026-10-31").dataset.level).toBe("0");
    // Home has one fixed view: no Activity/Chart switch and no window tabs.
    expect(screen.queryByRole("group", { name: "Activity view" })).toBeNull();
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  it("opens the Execution page on the selected day and names its exact counts", () => {
    mocks.activity = quarter({ "2026-11-01": { failed: 1, completed: 2 } });
    render(<HomeExecutionActivity />);

    const link = dayLink("2026-11-01");
    expect(link.getAttribute("href")).toBe("/execution?date=20261101");
    expect(link).toHaveAccessibleName("Sun, Nov 1, 2026: 3 executions, 2 completed, 1 failed");
    expect(dayLink("2026-10-31")).toHaveAccessibleName("Sat, Oct 31, 2026: 0 executions");
  });

  it("keeps the day grid to one tab stop and moves between days with arrow keys", () => {
    mocks.activity = quarter({ "2026-11-02": { completed: 1 } });
    render(<HomeExecutionActivity />);

    const links = within(grid()).getAllByRole("link");
    expect(links.filter((link) => link.tabIndex === 0)).toHaveLength(1);
    const last = dayLink("2026-11-02");
    expect(last.tabIndex).toBe(0);

    last.focus();
    fireEvent.keyDown(last, { key: "ArrowUp" });
    expect(document.activeElement).toBe(dayLink("2026-11-01"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(dayLink("2026-10-25"));
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement).toBe(dayLink("2026-08-05"));
    expect(dayLink("2026-08-05").tabIndex).toBe(0);
  });

  it("shows a skeleton while loading", () => {
    mocks.state = { isLoading: true, isError: false };
    render(<HomeExecutionActivity />);

    expect(document.querySelector(".skeleton")).not.toBeNull();
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("reports a load failure", () => {
    mocks.state = { isLoading: false, isError: true };
    render(<HomeExecutionActivity />);

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load execution activity.");
  });

  it("shows a calm empty state when the project ran nothing in the window", () => {
    mocks.activity = quarter();
    render(<HomeExecutionActivity />);

    expect(screen.getByText("No executions in the last 90 days")).toBeTruthy();
    expect(screen.queryByRole("group")).toBeNull();
  });
});
