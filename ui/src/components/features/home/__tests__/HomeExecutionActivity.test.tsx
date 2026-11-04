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

vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ projectId: "project-1" }) }));

function bucket(date: string, counts: Partial<Record<string, number>> = {}) {
  const base = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };
  const merged = { ...base, ...counts };
  return { date, ...merged, total: Object.values(merged).reduce((a, b) => a + b, 0) };
}

/** A 30-day window ending 2026-11-02, with the given counts on chosen days. */
function month(counts: Record<string, Partial<Record<string, number>>> = {}) {
  const end = Date.UTC(2026, 10, 2);
  const buckets = Array.from({ length: 30 }, (_, offset) => {
    const date = new Date(end - (29 - offset) * 86_400_000).toISOString().slice(0, 10);
    return bucket(date, counts[date]);
  });
  return {
    chip_id: null,
    days: 30,
    timezone: "Asia/Tokyo",
    since: buckets[0].date,
    until: buckets[29].date,
    buckets,
  };
}

afterEach(() => {
  cleanup();
  mocks.activity = null;
  mocks.state = { isLoading: false, isError: false };
  mocks.lastParams = undefined;
});

function dayLinks() {
  return within(screen.getByRole("group", { name: /Executions per day/ })).getAllByRole("link");
}

function dayLink(date: string) {
  const link = dayLinks().find((item) => item.dataset.date === date);
  if (!link) throw new Error(`No column for ${date}`);
  return link;
}

function blocksOf(date: string) {
  return Array.from(dayLink(date).querySelectorAll<HTMLElement>("[data-status]")).map((block) => ({
    status: block.dataset.status,
    executions: Number(block.dataset.executions),
    partial: block.dataset.partial === "true",
  }));
}

describe("HomeExecutionActivity", () => {
  it("requests the last 30 days for the whole project, not one chip", () => {
    mocks.activity = month();
    render(<HomeExecutionActivity />);

    expect(mocks.lastParams).toMatchObject({ days: 30 });
    expect(mocks.lastParams).not.toHaveProperty("chip_id");
  });

  it("summarizes the month and draws one block per execution in status order", () => {
    mocks.activity = month({
      "2026-11-01": { failed: 1, completed: 2 },
      "2026-11-02": { running: 1 },
    });
    render(<HomeExecutionActivity />);

    expect(screen.getByTestId("home-activity-total")).toHaveTextContent("4executions · 1 failed");
    const legend = within(screen.getByRole("list", { name: "Executions by status" }));
    expect(legend.getByText(/Completed/)).toHaveTextContent("Completed 2");
    expect(legend.getByText(/Failed/)).toHaveTextContent("Failed 1");
    expect(legend.queryByText(/Cancelled/)).toBeNull();
    expect(dayLinks()).toHaveLength(30);
    expect(blocksOf("2026-11-01").map((block) => block.status)).toEqual([
      "completed",
      "completed",
      "failed",
    ]);
    expect(screen.getByTestId("home-activity-scale")).toHaveTextContent("1 block = 1 execution");
  });

  it("bounds a busy day to 12 blocks with a labeled 1-2-5 scale and partly filled remainders", () => {
    mocks.activity = month({
      "2026-11-02": { completed: 20, failed: 3 },
      "2026-11-01": { failed: 1 },
    });
    render(<HomeExecutionActivity />);

    // 23 executions fit 12 blocks at a scale of 2: 10 completed and 2 failed, one of them partial.
    const blocks = blocksOf("2026-11-02");
    expect(blocks).toHaveLength(12);
    expect(blocks.filter((block) => block.partial)).toEqual([
      { status: "failed", executions: 1, partial: true },
    ]);
    expect(blocks.reduce((acc, block) => acc + block.executions, 0)).toBe(23);
    // A single execution on a quiet day is still drawn, as a half-filled block.
    expect(blocksOf("2026-11-01")).toEqual([{ status: "failed", executions: 1, partial: true }]);
    const half = dayLink("2026-11-01").querySelector<HTMLElement>("[data-status]");
    expect(half?.style.height).toBe("50%");
    expect(screen.getByTestId("home-activity-scale")).toHaveTextContent(
      "1 block = 2 executions, a partly filled block holds fewer",
    );
  });

  it("links every day to the Execution page and names its exact counts", () => {
    mocks.activity = month({ "2026-11-01": { completed: 2, failed: 1 } });
    render(<HomeExecutionActivity />);

    expect(dayLinks().every((link) => link.getAttribute("href") === "/execution")).toBe(true);
    expect(dayLink("2026-11-01")).toHaveAccessibleName(
      "Sun, Nov 1, 2026: 3 executions, 2 completed, 1 failed",
    );
  });

  it("keeps the day grid to one tab stop and moves between days with arrow keys", () => {
    mocks.activity = month({ "2026-11-02": { completed: 1 } });
    render(<HomeExecutionActivity />);

    const links = dayLinks();
    expect(links.filter((link) => link.tabIndex === 0)).toEqual([links[29]]);

    links[29].focus();
    fireEvent.keyDown(links[29], { key: "ArrowLeft" });
    expect(document.activeElement).toBe(links[28]);
    fireEvent.keyDown(links[28], { key: "Home" });
    expect(document.activeElement).toBe(links[0]);
    expect(links[0].tabIndex).toBe(0);
    fireEvent.keyDown(links[0], { key: "ArrowLeft" });
    expect(document.activeElement).toBe(links[0]);
    fireEvent.keyDown(links[0], { key: "End" });
    expect(document.activeElement).toBe(links[29]);
  });

  it("shows a calm empty state when the project ran nothing this month", () => {
    mocks.activity = month();
    render(<HomeExecutionActivity />);

    expect(screen.getByText("No executions in the last 30 days")).toBeInTheDocument();
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("reports a failed load instead of an empty month", () => {
    mocks.state = { isLoading: false, isError: true };
    render(<HomeExecutionActivity />);

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load execution activity.");
    expect(screen.queryByText("No executions in the last 30 days")).toBeNull();
  });

  it("shows a placeholder while loading", () => {
    mocks.state = { isLoading: true, isError: false };
    const { container } = render(<HomeExecutionActivity />);

    expect(container.querySelector(".skeleton")).not.toBeNull();
    expect(screen.queryByRole("group")).toBeNull();
  });
});
